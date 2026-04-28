"""
Auraya Backend — FastAPI entry point.

Endpoints:
  POST /api/v1/segment      → SAM segmentation via Replicate
  POST /api/v1/generate-3d  → 3D mesh via Tripo AI (async, returns task_id)
  GET  /api/v1/mesh/{id}    → Poll mesh status
  WS   /ws/{task_id}        → Real-time progress stream
  GET  /health              → Health check
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.middleware.rate_limiter import limiter
from app.routers import mesh, segmentation

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

ASSET_DIR = Path(os.getenv("ASSET_DIR", "./assets"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Auraya backend ready. Assets dir: %s", ASSET_DIR.resolve())
    yield
    logger.info("Auraya backend shutting down.")


app = FastAPI(
    title="Auraya API",
    description="AR Jewelry Try-On — backend service",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # lock down to your domain in production
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Static asset serving ──────────────────────────────────────────────────────
app.mount("/assets", StaticFiles(directory=str(ASSET_DIR)), name="assets")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(segmentation.router, prefix="/api/v1", tags=["segmentation"])
app.include_router(mesh.router,         prefix="/api/v1", tags=["mesh"])


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "service": "auraya-backend", "version": "1.0.0"}
