"""
Cloudinary storage service.

Provides a public URL for images so that Replicate and Tripo AI
can fetch them. Images are tagged with 'auraya' and auto-deleted after 24h
via a Cloudinary upload preset (configure in Cloudinary dashboard).
"""
from __future__ import annotations

import base64
import io
import logging
import os
import uuid

import cloudinary
import cloudinary.uploader

logger = logging.getLogger(__name__)


def _init():
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", ""),
        api_key=os.getenv("CLOUDINARY_API_KEY", ""),
        api_secret=os.getenv("CLOUDINARY_API_SECRET", ""),
        secure=True,
    )


async def upload_image(image_bytes: bytes, filename: str = "") -> str:
    """
    Upload raw image bytes to Cloudinary.

    Returns:
        Public HTTPS URL of the uploaded image.
    """
    _init()
    public_id = f"auraya/raw/{uuid.uuid4().hex}"
    result = cloudinary.uploader.upload(
        image_bytes,
        public_id=public_id,
        resource_type="image",
        tags=["auraya", "raw"],
        overwrite=False,
    )
    url: str = result["secure_url"]
    logger.info("Uploaded raw image → %s", url)
    return url


async def upload_png(png_bytes: bytes) -> str:
    """
    Upload a transparent PNG (segmented jewelry) to Cloudinary.

    Returns:
        Public HTTPS URL of the PNG.
    """
    _init()
    public_id = f"auraya/segmented/{uuid.uuid4().hex}"
    result = cloudinary.uploader.upload(
        png_bytes,
        public_id=public_id,
        resource_type="image",
        format="png",
        tags=["auraya", "segmented"],
        overwrite=False,
    )
    url: str = result["secure_url"]
    logger.info("Uploaded segmented PNG → %s", url)
    return url
