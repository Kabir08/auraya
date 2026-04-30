# Auraya — Backend Service Specification (FastAPI)

---

## Overview

The backend is a **Python FastAPI** service responsible for:
1. Receiving images from the web frontend (file upload or webcam snapshot)
2. Running SAM segmentation (or RMBG fallback)
3. Classifying jewelry type
4. Calling Meshy.ai for 3D generation
5. Serving `.glb` assets back to the browser
6. Pushing progress via WebSocket
7. **Serving the static web frontend** (`frontend/` directory mounted at `/`)

**Deployment:** Hugging Face Spaces — Docker container. HF Spaces exposes port 7860.

---

## Tech Stack

| Component | Library / Tool | Version Target |
|:----------|:--------------|:---------------|
| Web framework | FastAPI | 0.115+ |
| ASGI server | Uvicorn + Gunicorn | - |
| Image processing | Pillow, OpenCV | - |
| Segmentation | `segment-anything-2` (Meta) | SAM 2 |
| Background removal | `rembg` (RMBG-1.4) | fallback |
| Classifier | `timm` (MobileNetV3) | fine-tuned |
| 3D generation | Meshy.ai REST API | v1 |
| 3D fallback | `tsr` (TripoSR) | self-hosted |
| Mesh optimization | `gltfpack` (CLI) | - |
| Task queue | **Background tasks** (`fastapi.BackgroundTasks`) | Replaces Celery+Redis — simpler for HF Spaces |
| File storage | `/tmp` (ephemeral on HF Spaces) | Assets cleaned up after 1h |
| Rate limiting | `slowapi` | - |
| Auth | API key header (`X-Auraya-Key`) | Phase 1 simple |

---

## API Endpoints

### POST `/api/v1/segment`
Upload an image and receive a transparent PNG.

**Request:**
```
Content-Type: multipart/form-data
Body:
  file: <image file>  (jpg/png/webp, max 10MB)
```

**Response (200):**
```json
{
  "task_id": "seg_abc123",
  "status": "completed",
  "jewelry_type": "necklace",
  "classifier_confidence": 0.92,
  "png_url": "/assets/seg_abc123.png"
}
```

**Response (400):**
```json
{
  "error": "NOT_JEWELRY",
  "message": "Uploaded image was not recognized as jewelry (confidence: 0.41). Please upload a clear photo of a jewelry item.",
  "classifier_confidence": 0.41
}
```

---

### POST `/api/v1/generate-3d`
Kick off 3D mesh generation from a segmented PNG.

**Request:**
```json
{
  "png_url": "/assets/seg_abc123.png",
  "jewelry_type": "necklace",
  "quality": "medium"   // "draft" | "medium" | "high"
}
```

**Response (202 Accepted):**
```json
{
  "task_id": "mesh_xyz789",
  "status": "queued",
  "estimated_seconds": 25,
  "ws_channel": "/ws/mesh_xyz789"
}
```

---

### GET `/api/v1/mesh/{task_id}`
Poll mesh generation status.

**Response:**
```json
{
  "task_id": "mesh_xyz789",
  "status": "processing",   // "queued" | "processing" | "completed" | "failed"
  "progress": 65,
  "glb_url": null           // populated when status = "completed"
}
```

---

### WebSocket `/ws/{task_id}`
Real-time progress stream for mesh generation.

**Server → Client messages:**
```json
{ "type": "progress", "percent": 30, "message": "Generating mesh..." }
{ "type": "progress", "percent": 75, "message": "Applying textures..." }
{ "type": "completed", "glb_url": "/assets/mesh_xyz789.glb", "file_size_kb": 840 }
{ "type": "error", "code": "MESHY_TIMEOUT", "message": "3D generation timed out. Retrying..." }
```

---

### GET `/assets/{filename}`
Serve generated PNG and GLB files (rate-limited, token-validated).

---

## Service Architecture

```
FastAPI App
├── routers/
│   ├── segmentation.py     → /api/v1/segment
│   ├── mesh.py             → /api/v1/generate-3d, /api/v1/mesh/{id}
│   └── assets.py           → /assets/{filename}
├── services/
│   ├── classifier_service.py   → MobileNetV3 jewelry detection
│   ├── sam_service.py          → SAM 2 segmentation
│   ├── rembg_service.py        → RMBG-1.4 fallback
│   ├── meshy_service.py        → Meshy.ai API client
│   └── triposr_service.py      → TripoSR self-hosted fallback
├── workers/
│   └── mesh_worker.py          → Celery async task
├── middleware/
│   ├── rate_limiter.py         → slowapi
│   └── auth.py                 → API key check
└── utils/
    ├── image_validation.py     → size, MIME, blur detection
    └── mesh_optimizer.py       → gltfpack compression
```

---

## Safety & Rate Limits

```python
# rate_limiter.py
LIMITS = {
    "/api/v1/segment":     "10/minute",
    "/api/v1/generate-3d": "5/minute",
    "/assets/":            "60/minute",
}
```

- Max image upload: **10 MB**
- Max concurrent Meshy.ai jobs per user: **2**
- Generated asset TTL: **1 hour** (FastAPI BackgroundTask scheduled cleanup — HF Spaces `/tmp` is ephemeral anyway)
- SAM timeout → fallback to RMBG after **3 seconds**
- Meshy.ai timeout → fallback to TripoSR after **45 seconds**

---

## Environment Variables

```env
# .env (backend)

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=false

# API Keys
MESHY_API_KEY=your_meshy_key_here
# Future providers (leave blank until ready)
RODIN_API_KEY=
STABILITY_API_KEY=

# SAM Model
SAM_CHECKPOINT_PATH=./models/sam2_hiera_large.pt
SAM_MODEL_TYPE=vit_h

# Storage
ASSET_DIR=/tmp/auraya_assets
ASSET_BASE_URL=https://<your-hf-space>.hf.space/assets

# Security
AURAYA_API_KEY=change_me_in_production
MAX_UPLOAD_MB=10
```

---

## Hardware Requirements (Dev & HF Spaces)

| Mode | Minimum | Notes |
|:-----|:--------|:------|
| HF Spaces CPU tier | 2 vCPU, 16GB RAM | Use RMBG-1.4 + Meshy.ai only (no SAM GPU needed) |
| HF Spaces GPU tier | T4 (16GB) | Enables SAM 2 inference |
| TripoSR fallback | 12GB GPU VRAM | Only if Meshy.ai is unavailable |
| Local dev (no GPU) | 8GB RAM, CPU | `rembg` fallback only |

> For HF Spaces free tier (CPU), disable SAM 2 and use `rembg` (RMBG-1.4) at ~1-2s/image. Meshy.ai handles all 3D generation — no local GPU needed for that.

---

## HF Spaces Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for OpenCV + rembg
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

# HF Spaces requires port 7860
ENV PORT=7860
EXPOSE 7860

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

### `main.py` — Mount frontend as static files

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# API routes registered first
app.include_router(segmentation_router, prefix="/api/v1")
app.include_router(mesh_router,         prefix="/api/v1")

# Frontend SPA served at root — must be last
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
```

### HF Spaces `README.md` header (Space config)

```yaml
---
title: Auraya
emoji: 💎
colorFrom: purple
colorTo: pink
sdk: docker
pinned: false
---
```

### Environment Secrets (set in HF Space settings, not in code)

```
MESHY_API_KEY       ← required
AURAYA_API_KEY      ← optional, for rate-limit bypass
```
