"""Image Storage Service for Daily Post Visuals.

Uploads images directly to Supabase Storage (or S3/Cloudinary) for permanent,
high-speed CDN delivery, preventing hotlinking and broken image links.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

import httpx

logger = logging.getLogger("StorageService")


class StorageService:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_KEY", "")
        self.bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "portal-covers")

    async def persist_image_from_url(self, source_url: str, slug: str) -> str:
        """Downloads image from source URL and uploads to cloud storage bucket.
        Returns the permanent CDN public URL, or falls back to source_url on failure."""
        if not self.supabase_url or not self.supabase_key:
            logger.info("No Supabase storage credentials configured; keeping original image CDN URL")
            return source_url

        try:
            # 1. Download image bytes
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                res = await client.get(source_url)
                if res.status_code != 200:
                    return source_url
                content_type = res.headers.get("content-type", "image/jpeg").split(";")[0]
                image_bytes = res.content

            # 2. Upload to Supabase Storage Bucket
            ext = "png" if "png" in content_type else "jpg"
            filename = f"{slug}-{uuid.uuid4().hex[:6]}.{ext}"
            upload_url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{filename}"

            headers = {
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": content_type,
                "x-upsert": "true",
            }

            async with httpx.AsyncClient(timeout=20.0) as client:
                up_res = await client.post(upload_url, content=image_bytes, headers=headers)
                if up_res.status_code in (200, 201):
                    public_url = f"{self.supabase_url}/storage/v1/object/public/{self.bucket}/{filename}"
                    logger.info(f"Persisted cover image to Supabase Storage: {public_url}")
                    return public_url
                else:
                    logger.warning(f"Supabase upload returned {up_res.status_code}: {up_res.text}")

        except Exception as e:
            logger.warning(f"Failed to persist image to cloud storage: {e}")

        return source_url
