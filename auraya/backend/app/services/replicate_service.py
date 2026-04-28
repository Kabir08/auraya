"""
Replicate service — SAM 2 segmentation + rembg fallback.

Primary  : cjwbw/rembg  (fast, CPU, direct transparent PNG)
Advanced : meta/sam-2   (higher accuracy, needs GPU, auto mode)
"""
from __future__ import annotations

import base64
import io
import logging
import os
from typing import Optional

import httpx
import replicate
from PIL import Image

logger = logging.getLogger(__name__)

# ── Model versions ─────────────────────────────────────────────────────────────
REMBG_MODEL      = "cjwbw/rembg:fb8af171cfa1616ddcf1242c093f9c46bcada5ad4cf6f2fbe8b81b330ec5c003"
SAM2_MODEL       = "meta/sam-2"


async def segment_jewelry(image_url: str, use_sam: bool = False) -> dict:
    """
    Remove background from a jewelry image.

    Args:
        image_url : Public URL of the raw jewelry photo.
        use_sam   : If True, use SAM 2 for more precise segmentation.
                    Falls back to rembg on SAM failure.

    Returns:
        {
          "png_b64": "<base64-encoded transparent PNG>",
          "model_used": "rembg" | "sam2",
          "jewelry_type": "unknown"   ← classification placeholder
        }
    """
    try:
        if use_sam:
            return await _segment_with_sam2(image_url)
        return await _segment_with_rembg(image_url)
    except Exception as exc:
        logger.warning("Primary segmentation failed (%s). Falling back to rembg.", exc)
        return await _segment_with_rembg(image_url)


# ─── rembg (primary fast path) ────────────────────────────────────────────────

async def _segment_with_rembg(image_url: str) -> dict:
    logger.info("Running rembg segmentation on %s", image_url)
    output = replicate.run(
        REMBG_MODEL,
        input={"image": image_url},
    )
    # output is a FileOutput URL string pointing to a PNG with alpha channel
    png_url: str = str(output)
    png_bytes = await _download_bytes(png_url)
    png_b64   = base64.b64encode(png_bytes).decode()
    return {"png_b64": png_b64, "model_used": "rembg", "jewelry_type": "unknown"}


# ─── SAM 2 (high-accuracy path) ───────────────────────────────────────────────

async def _segment_with_sam2(image_url: str) -> dict:
    logger.info("Running SAM 2 segmentation on %s", image_url)

    # SAM 2 returns a list of masks; we pick the largest central one and
    # apply it to the original image to produce a transparent PNG.
    output = replicate.run(
        SAM2_MODEL,
        input={
            "image":     image_url,
            "task_type": "auto",
        },
    )

    # output["masks"] is a list of mask image URLs (black/white PNGs)
    masks: list = output.get("masks", [])
    if not masks:
        raise ValueError("SAM 2 returned no masks.")

    # Download original image + masks, pick the best one
    orig_bytes = await _download_bytes(image_url)
    orig_img   = Image.open(io.BytesIO(orig_bytes)).convert("RGBA")

    best_mask_url = await _pick_best_mask(masks, orig_img.size)
    mask_bytes    = await _download_bytes(best_mask_url)
    mask_img      = Image.open(io.BytesIO(mask_bytes)).convert("L")

    # Apply mask as alpha channel
    orig_img.putalpha(mask_img)

    buf = io.BytesIO()
    orig_img.save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode()

    return {"png_b64": png_b64, "model_used": "sam2", "jewelry_type": "unknown"}


async def _pick_best_mask(mask_urls: list[str], image_size: tuple[int, int]) -> str:
    """Return the mask URL whose non-zero area is largest and most centred."""
    import numpy as np

    cx, cy   = image_size[0] / 2, image_size[1] / 2
    best_url = mask_urls[0]
    best_score = -1.0

    for url in mask_urls:
        try:
            data  = await _download_bytes(url)
            arr   = np.array(Image.open(io.BytesIO(data)).convert("L"))
            area  = float((arr > 128).sum())
            if area == 0:
                continue
            ys, xs = np.where(arr > 128)
            dist  = float(((xs.mean() - cx) ** 2 + (ys.mean() - cy) ** 2) ** 0.5)
            score = area / (1.0 + dist)
            if score > best_score:
                best_score = score
                best_url   = url
        except Exception:
            continue

    return best_url


async def _download_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content
