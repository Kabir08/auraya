"""
POST /api/v1/generate-3d   → kick off Tripo AI mesh generation (returns task_id)
GET  /api/v1/mesh/{id}     → poll task status
WS   /ws/{task_id}         → real-time progress stream
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.middleware.rate_limiter import limiter
from app.services.tripo_service import (
    TripoStatus,
    create_mesh_task,
    extract_glb_url,
    poll_task,
)

logger = logging.getLogger(__name__)
router = APIRouter()

RATE_LIMIT = os.getenv("RATE_LIMIT_MESH", "5/minute")

# In-memory task cache (replace with Redis in production)
_task_store: dict[str, dict] = {}


# ─── Request / Response models ────────────────────────────────────────────────

class Generate3DRequest(BaseModel):
    png_url:      str
    jewelry_type: str  = "necklace"
    quality:      str  = "medium"   # draft | medium | high (ignored by Tripo for now)


class Generate3DResponse(BaseModel):
    task_id:           str
    status:            str
    estimated_seconds: int
    ws_channel:        str


class MeshStatusResponse(BaseModel):
    task_id:  str
    status:   str
    progress: int
    glb_url:  Optional[str] = None
    error:    Optional[str] = None


# ─── POST /generate-3d ────────────────────────────────────────────────────────

@router.post("/generate-3d", response_model=Generate3DResponse, status_code=202)
@limiter.limit(RATE_LIMIT)
async def generate_3d(request: Request, body: Generate3DRequest):
    """
    Start 3D mesh generation for a segmented jewelry PNG.
    Returns immediately with a `task_id`; use the WebSocket for live progress.
    """
    try:
        task_id = await create_mesh_task(body.png_url, body.jewelry_type)
    except Exception as exc:
        logger.error("Tripo AI task creation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"3D generation service error: {exc}") from exc

    _task_store[task_id] = {"status": TripoStatus.QUEUED, "progress": 0, "glb_url": None}

    return Generate3DResponse(
        task_id           = task_id,
        status            = TripoStatus.QUEUED,
        estimated_seconds = 25,
        ws_channel        = f"/ws/{task_id}",
    )


# ─── GET /mesh/{task_id} ─────────────────────────────────────────────────────

@router.get("/mesh/{task_id}", response_model=MeshStatusResponse)
async def mesh_status(task_id: str):
    """Poll the current status of a mesh generation task."""
    cached = _task_store.get(task_id)
    if cached:
        return MeshStatusResponse(task_id=task_id, **cached)

    # Not in cache → ask Tripo AI directly (e.g. after server restart)
    try:
        from app.services.tripo_service import _headers
        import httpx, os
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://api.tripo3d.ai/v2/openapi/task/{task_id}",
                headers=_headers(),
            )
            r.raise_for_status()
            body_data = r.json()["data"]
            status   = body_data.get("status", "unknown")
            progress = body_data.get("progress", 0)
            glb_url  = None
            if status == TripoStatus.SUCCESS:
                glb_url = extract_glb_url(body_data)
            return MeshStatusResponse(
                task_id=task_id, status=status, progress=progress, glb_url=glb_url
            )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}") from exc


# ─── WebSocket /ws/{task_id} ─────────────────────────────────────────────────

@router.websocket("/ws/{task_id}")
async def mesh_progress_ws(websocket: WebSocket, task_id: str):
    """
    Stream real-time progress for a mesh generation task.

    Messages (JSON):
      { "type": "progress", "percent": 40, "message": "..." }
      { "type": "completed", "glb_url": "...", "file_size_kb": 820 }
      { "type": "error",     "code": "TRIPO_FAILED", "message": "..." }
    """
    await websocket.accept()
    logger.info("WS connected for task %s", task_id)

    try:
        from app.services import tripo_service as ts
        import httpx

        deadline = asyncio.get_event_loop().time() + ts.MAX_POLL_SECONDS

        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                r = await client.get(
                    f"{ts.TRIPO_BASE}/task/{task_id}",
                    headers=ts._headers(),
                )
                r.raise_for_status()
                data     = r.json()["data"]
                status   = data.get("status", "")
                progress = data.get("progress", 0)

                _task_store[task_id] = {"status": status, "progress": progress, "glb_url": None}

                await websocket.send_text(json.dumps({
                    "type":    "progress",
                    "percent": progress,
                    "message": f"Status: {status}",
                }))

                if status == TripoStatus.SUCCESS:
                    glb_url = extract_glb_url(data)
                    _task_store[task_id]["glb_url"] = glb_url
                    await websocket.send_text(json.dumps({
                        "type":    "completed",
                        "glb_url": glb_url,
                    }))
                    break

                if status in (TripoStatus.FAILED, TripoStatus.CANCELLED):
                    await websocket.send_text(json.dumps({
                        "type":    "error",
                        "code":    "TRIPO_FAILED",
                        "message": f"Task ended with status: {status}",
                    }))
                    break

                if asyncio.get_event_loop().time() > deadline:
                    await websocket.send_text(json.dumps({
                        "type":    "error",
                        "code":    "TIMEOUT",
                        "message": "3D generation timed out. Try again.",
                    }))
                    break

                await asyncio.sleep(ts.POLL_INTERVAL_S)

    except WebSocketDisconnect:
        logger.info("WS disconnected for task %s", task_id)
    except Exception as exc:
        logger.error("WS error for task %s: %s", task_id, exc)
        try:
            await websocket.send_text(json.dumps({
                "type": "error", "code": "INTERNAL", "message": str(exc)
            }))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
