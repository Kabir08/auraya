"""
POST /api/v1/segment

Receives a jewelry image, removes the background via Replicate (rembg / SAM 2),
and returns a base64-encoded transparent PNG + a Cloudinary-hosted PNG URL.
"""
from __future__ import annotations

import base64
import logging
import os

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.middleware.rate_limiter import limiter
from app.services.replicate_service import segment_jewelry
from app.services.storage_service import upload_image, upload_png
from app.utils.image_validation import validate_image

logger = logging.getLogger(__name__)
router = APIRouter()

RATE_LIMIT = os.getenv("RATE_LIMIT_SEGMENT", "10/minute")


class SegmentResponse(BaseModel):
    png_url:              str
    png_b64:              str
    model_used:           str
    jewelry_type:         str
    classifier_confidence: float


@router.post("/segment", response_model=SegmentResponse)
@limiter.limit(RATE_LIMIT)
async def segment(
    request: Request,
    file:    UploadFile = File(...),
    use_sam: bool       = False,
):
    """
    Upload a jewelry photo → returns a transparent PNG.

    - **file**: the raw jewelry image (jpg / png / webp, max 10 MB).
    - **use_sam**: set `true` to use SAM 2 for higher-accuracy segmentation
      (slower; defaults to fast rembg).
    """
    image_bytes = await file.read()

    # Validate (raises HTTPException on failure)
    validate_image(image_bytes, file.content_type)

    # Upload to Cloudinary so Replicate can fetch it via URL
    try:
        image_url = await upload_image(image_bytes, file.filename or "jewelry.jpg")
    except Exception as exc:
        logger.error("Cloudinary upload failed: %s", exc)
        raise HTTPException(status_code=502, detail="Image storage service unavailable.") from exc

    # Run segmentation
    try:
        result = await segment_jewelry(image_url, use_sam=use_sam)
    except Exception as exc:
        logger.error("Segmentation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Segmentation failed: {exc}") from exc

    # Upload the transparent PNG to Cloudinary (Tripo AI needs a public URL)
    png_bytes = base64.b64decode(result["png_b64"])
    try:
        png_url = await upload_png(png_bytes)
    except Exception as exc:
        logger.error("PNG upload failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to store segmented PNG.") from exc

    return SegmentResponse(
        png_url               = png_url,
        png_b64               = result["png_b64"],
        model_used            = result["model_used"],
        jewelry_type          = result.get("jewelry_type", "unknown"),
        classifier_confidence = result.get("confidence", 1.0),
    )
