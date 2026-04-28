"""
Image validation utilities.

Checks performed:
  1. File size ≤ MAX_UPLOAD_MB
  2. MIME type is in the allow-list (jpg/png/webp)
  3. Pillow can actually decode the image (not truncated / not a polyglot)
  4. Basic blur detection (Laplacian variance)
"""
from __future__ import annotations

import io
import os
from typing import Optional

from fastapi import HTTPException
from PIL import Image, ImageFilter

MAX_MB   = int(os.getenv("MAX_UPLOAD_MB", "10"))
MAX_BYTES = MAX_MB * 1024 * 1024

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}

BLUR_THRESHOLD = 50.0   # Laplacian variance below this → "too blurry"
MIN_DIMENSION  = 64     # reject tiny/icon images


def validate_image(data: bytes, content_type: Optional[str]) -> Image.Image:
    """
    Validate image bytes. Returns an open PIL Image on success.
    Raises HTTPException on any failure.
    """
    # ── 1. Size ────────────────────────────────────────────────────────────────
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max allowed: {MAX_MB} MB.",
        )

    # ── 2. MIME ────────────────────────────────────────────────────────────────
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: '{mime}'. Allowed: jpg, png, webp.",
        )

    # ── 3. Decodability ────────────────────────────────────────────────────────
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()          # raises on corrupt/truncated
        img = Image.open(io.BytesIO(data))  # re-open after verify
        img.load()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Image could not be decoded: {exc}",
        ) from exc

    # ── 4. Dimensions ──────────────────────────────────────────────────────────
    w, h = img.size
    if w < MIN_DIMENSION or h < MIN_DIMENSION:
        raise HTTPException(
            status_code=422,
            detail=f"Image too small ({w}×{h}). Minimum: {MIN_DIMENSION}px on each side.",
        )

    # ── 5. Blur detection (Laplacian variance) ─────────────────────────────────
    gray = img.convert("L")
    lap  = gray.filter(ImageFilter.Kernel(
        size=3,
        kernel=[ 0,  1,  0,
                 1, -4,  1,
                 0,  1,  0],
        scale=1, offset=128,
    ))
    import statistics
    pixels   = list(lap.getdata())
    variance = statistics.variance(pixels)
    if variance < BLUR_THRESHOLD:
        raise HTTPException(
            status_code=422,
            detail="Image appears too blurry. Please upload a sharper photo.",
        )

    return img
