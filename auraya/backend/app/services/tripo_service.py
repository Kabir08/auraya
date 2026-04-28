"""
Tripo AI service — image → .glb 3D mesh generation.

API docs: https://platform.tripo3d.ai/docs/api-reference
Flow:
  1. POST /task  → { task_id }
  2. Poll GET /task/{id} every 3s until status ∈ {success, failed}
  3. Return .glb URL from result.pbr_model.url
"""
from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TRIPO_BASE = "https://api.tripo3d.ai/v2/openapi"
POLL_INTERVAL_S  = 3
MAX_POLL_SECONDS = 120


class TripoStatus(str, Enum):
    QUEUED     = "queued"
    RUNNING    = "running"
    SUCCESS    = "success"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


def _headers() -> dict:
    key = os.getenv("TRIPO_API_KEY", "")
    if not key:
        raise EnvironmentError("TRIPO_API_KEY is not set.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def create_mesh_task(image_url: str, jewelry_type: str = "necklace") -> str:
    """
    Submit an image-to-3D task to Tripo AI.

    Returns:
        task_id (str)
    """
    payload = {
        "type": "image_to_model",
        "file": {
            "type": "png",
            "url":  image_url,
        },
        "model_version": "v2.5-20250123",   # latest stable as of 2026-04
        "texture":       True,
        "pbr":           True,
        "face_limit":    10000,              # reasonable for mobile AR
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{TRIPO_BASE}/task",
            json=payload,
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()

    if data.get("code", -1) != 0:
        raise RuntimeError(f"Tripo AI error: {data}")

    task_id: str = data["data"]["task_id"]
    logger.info("Tripo AI task created: %s", task_id)
    return task_id


async def poll_task(task_id: str) -> dict:
    """
    Poll Tripo AI until the task finishes or times out.

    Returns the full task data dict on success, raises on failure/timeout.
    """
    deadline = asyncio.get_event_loop().time() + MAX_POLL_SECONDS

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            r = await client.get(
                f"{TRIPO_BASE}/task/{task_id}",
                headers=_headers(),
            )
            r.raise_for_status()
            body = r.json()

            if body.get("code", -1) != 0:
                raise RuntimeError(f"Tripo AI poll error: {body}")

            task_data: dict = body["data"]
            status = task_data.get("status", "")
            progress = task_data.get("progress", 0)
            logger.debug("Tripo task %s — status=%s  progress=%d%%", task_id, status, progress)

            if status == TripoStatus.SUCCESS:
                return task_data
            if status in (TripoStatus.FAILED, TripoStatus.CANCELLED):
                raise RuntimeError(
                    f"Tripo AI task {task_id} ended with status={status}"
                )

            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(
                    f"Tripo AI task {task_id} did not complete within {MAX_POLL_SECONDS}s"
                )

            await asyncio.sleep(POLL_INTERVAL_S)


def extract_glb_url(task_data: dict) -> str:
    """Pull the .glb URL out of a completed Tripo task payload."""
    try:
        return task_data["result"]["pbr_model"]["url"]
    except KeyError:
        # Fallback to non-PBR model
        try:
            return task_data["result"]["model"]["url"]
        except KeyError as e:
            raise ValueError(f"Could not find .glb URL in Tripo response: {task_data}") from e


async def generate_3d(image_url: str, jewelry_type: str = "necklace") -> dict:
    """
    Full blocking pipeline: image URL → .glb URL.
    Use `create_mesh_task` + WebSocket progress stream for the async variant.
    """
    task_id  = await create_mesh_task(image_url, jewelry_type)
    task_data = await poll_task(task_id)
    glb_url   = extract_glb_url(task_data)
    return {"task_id": task_id, "glb_url": glb_url, "progress": 100}
