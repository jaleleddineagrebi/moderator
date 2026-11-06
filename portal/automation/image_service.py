"""Free Image Sourcing & AI Image Placeholder Service for Daily Posts.

Integrates:
1. Unsplash API (free tier: 50 requests/hour)
2. Pexels API (free tier: 200 requests/hour)
3. Wikimedia Commons Open Media Search
4. Curated high-resolution fallback placeholder images (neuroscience & AI aesthetic)
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("ImageService")

FALLBACK_NEURO_AI_IMAGES = [
    {
        "url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
        "credit": "Milad Fakurian via Unsplash",
    },
    {
        "url": "https://images.unsplash.com/photo-1507413245164-6160d8298b31?auto=format&fit=crop&w=1200&q=80",
        "credit": "Hal Gatewood via Unsplash",
    },
    {
        "url": "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
        "credit": "DeepMind via Unsplash",
    },
    {
        "url": "https://images.unsplash.com/photo-1617791160505-6f00504e3519?auto=format&fit=crop&w=1200&q=80",
        "credit": "Google DeepMind via Unsplash",
    },
]


@dataclass
class ImageResult:
    image_url: str
    credit: str


class ImageService:
    def __init__(self):
        self.unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
        self.pexels_key = os.getenv("PEXELS_API_KEY", "")

    async def get_image_for_post(self, query: str) -> ImageResult:
        """Finds a relevant image for a Psychology & AI post."""
        clean_query = query.replace("AI", "artificial intelligence").strip()

        # 1. Try Unsplash if key is present
        if self.unsplash_key:
            res = await self._search_unsplash(clean_query)
            if res:
                return res

        # 2. Try Pexels if key is present
        if self.pexels_key:
            res = await self._search_pexels(clean_query)
            if res:
                return res

        # 3. Try open Wikimedia Search (no API key required)
        res = await self._search_wikimedia(clean_query)
        if res:
            return res

        # 4. Fallback to curated neuroscience & generative AI visuals
        pick = random.choice(FALLBACK_NEURO_AI_IMAGES)
        logger.info("Using curated neuroscience/AI fallback cover visual")
        return ImageResult(image_url=pick["url"], credit=pick["credit"])

    async def _search_unsplash(self, query: str) -> Optional[ImageResult]:
        url = "https://api.unsplash.com/search/photos"
        headers = {"Authorization": f"Client-ID {self.unsplash_key}"}
        params = {"query": query, "orientation": "landscape", "per_page": 3}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    data = res.json()
                    results = data.get("results", [])
                    if results:
                        photo = results[0]
                        author = photo.get("user", {}).get("name", "Unknown")
                        return ImageResult(
                            image_url=photo["urls"]["regular"],
                            credit=f"Photo by {author} on Unsplash",
                        )
        except Exception as e:
            logger.warning(f"Unsplash API call failed: {e}")
        return None

    async def _search_pexels(self, query: str) -> Optional[ImageResult]:
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": self.pexels_key}
        params = {"query": query, "orientation": "landscape", "per_page": 3}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    data = res.json()
                    photos = data.get("photos", [])
                    if photos:
                        p = photos[0]
                        photographer = p.get("photographer", "Pexels Creator")
                        return ImageResult(
                            image_url=p["src"]["large"],
                            credit=f"Photo by {photographer} on Pexels",
                        )
        except Exception as e:
            logger.warning(f"Pexels API call failed: {e}")
        return None

    async def _search_wikimedia(self, query: str) -> Optional[ImageResult]:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": 3,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "format": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    pages = res.json().get("query", {}).get("pages", {})
                    for p in pages.values():
                        infos = p.get("imageinfo", [])
                        if infos:
                            img_url = infos[0].get("url")
                            if img_url and any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
                                return ImageResult(
                                    image_url=img_url,
                                    credit="Wikimedia Commons Open License",
                                )
        except Exception as e:
            logger.warning(f"Wikimedia search failed: {e}")
        return None
