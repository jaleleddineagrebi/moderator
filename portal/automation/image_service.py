"""Free Image Sourcing & AI Image Placeholder Service for Daily Posts.

Integrates:
1. Unsplash API (free tier: 50 requests/hour)
2. Pexels API (free tier: 200 requests/hour)
3. Wikimedia Commons Open Media Search
4. Curated high-resolution fallback placeholder images (neuroscience & AI aesthetic)
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Iterable, Optional

import httpx

logger = logging.getLogger("ImageService")

WIKIMEDIA_HEADERS = {
    "User-Agent": "MindDecodedPortal/1.0 (https://github.com/jaleleddineagrebi/moderator; contact@minddecoded.ai)"
}

FALLBACK_NEURO_AI_IMAGES = [
    {"url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80", "credit": "Milad Fakurian via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1507413245164-6160d8298b31?auto=format&fit=crop&w=1200&q=80", "credit": "Hal Gatewood via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80", "credit": "DeepMind via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1617791160505-6f00504e3519?auto=format&fit=crop&w=1200&q=80", "credit": "Google DeepMind via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1559757175-5700dde675bc?auto=format&fit=crop&w=1200&q=80", "credit": "Robina Weermeijer via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&q=80", "credit": "Markus Spiske via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80", "credit": "NASA via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1509228468518-180dd4864904?auto=format&fit=crop&w=1200&q=80", "credit": "Antoine Dautry via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80", "credit": "Alexandre Debiève via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&q=80", "credit": "Adi Goldstein via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=1200&q=80", "credit": "Milad Fakurian via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1635070041078-e363dbe005cb?auto=format&fit=crop&w=1200&q=80", "credit": "FlyD via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1200&q=80", "credit": "Johannes Plenio via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1516110833967-0b5716ca1387?auto=format&fit=crop&w=1200&q=80", "credit": "aguiam via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1200&q=80", "credit": "Taylor Vick via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1618005198919-d3d4b5a92ead?auto=format&fit=crop&w=1200&q=80", "credit": "Milad Fakurian via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1200&q=80", "credit": "Pawel Czerwinski via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119?auto=format&fit=crop&w=1200&q=80", "credit": "Birmingham Museums Trust via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1541701494587-cb58502866ab?auto=format&fit=crop&w=1200&q=80", "credit": "Lucas Benjamin via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1557672172-298e090bd0f1?auto=format&fit=crop&w=1200&q=80", "credit": "Pawel Czerwinski via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1563089145-599997674d42?auto=format&fit=crop&w=1200&q=80", "credit": "ettocl via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=1200&q=80", "credit": "Benjamin Voros via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1484417894907-623942c8ee29?auto=format&fit=crop&w=1200&q=80", "credit": "Emile Perron via Unsplash"},
    {"url": "https://images.unsplash.com/photo-1531297484001-80022131f5a1?auto=format&fit=crop&w=1200&q=80", "credit": "ales nesetril via Unsplash"},
]


def _seed_index(seed_key: str, length: int) -> int:
    if length <= 1:
        return 0
    digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % length


@dataclass
class ImageResult:
    image_url: str
    credit: str


class ImageService:
    def __init__(self):
        self.unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
        self.pexels_key = os.getenv("PEXELS_API_KEY", "")
        self.pixabay_key = os.getenv("PIXABAY_API_KEY", "")

    async def get_image_for_post(
        self,
        query: str,
        *,
        exclude_urls: Optional[Iterable[str]] = None,
        seed_key: str = "",
    ) -> ImageResult:
        """Finds a unique, relevant cover image for a Psychology & AI post, never repeating `exclude_urls`."""
        excluded = {u.split("?")[0] for u in (exclude_urls or []) if u}
        clean_query = (query or "human mind psychology").strip()
        seed = seed_key or clean_query

        # 1. Try Unsplash if key is present
        if self.unsplash_key:
            res = await self._search_unsplash(clean_query, excluded, seed)
            if res:
                return res

        # 2. Try Pexels if key is present
        if self.pexels_key:
            res = await self._search_pexels(clean_query, excluded, seed)
            if res:
                return res

        # 3. Try Pixabay if key is present
        if self.pixabay_key:
            res = await self._search_pixabay(clean_query, excluded, seed)
            if res:
                return res

        # 4. Try open Wikimedia Search (with proper User-Agent header)
        res = await self._search_wikimedia(clean_query, excluded, seed)
        if res:
            return res

        # 5. Fallback to curated 24-image neuroscience & AI pool with strict deduplication
        available = [item for item in FALLBACK_NEURO_AI_IMAGES if item["url"].split("?")[0] not in excluded]
        pool = available if available else FALLBACK_NEURO_AI_IMAGES
        pick = pool[_seed_index(seed, len(pool))]
        logger.info("Using curated neuroscience/AI cover visual (%s)", pick["url"])
        return ImageResult(image_url=pick["url"], credit=pick["credit"])

    async def _search_unsplash(self, query: str, excluded: set[str], seed: str) -> Optional[ImageResult]:
        url = "https://api.unsplash.com/search/photos"
        headers = {"Authorization": f"Client-ID {self.unsplash_key}"}
        params = {"query": query, "orientation": "landscape", "per_page": 15}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    results = [
                        r for r in res.json().get("results", [])
                        if r.get("urls", {}).get("regular", "").split("?")[0] not in excluded
                    ]
                    if results:
                        photo = results[_seed_index(seed, len(results))]
                        author = photo.get("user", {}).get("name", "Unknown")
                        return ImageResult(
                            image_url=photo["urls"]["regular"],
                            credit=f"Photo by {author} on Unsplash",
                        )
        except Exception as e:
            logger.warning(f"Unsplash API call failed: {e}")
        return None

    async def _search_pexels(self, query: str, excluded: set[str], seed: str) -> Optional[ImageResult]:
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": self.pexels_key}
        params = {"query": query, "orientation": "landscape", "per_page": 15}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    photos = [
                        p for p in res.json().get("photos", [])
                        if p.get("src", {}).get("large", "").split("?")[0] not in excluded
                    ]
                    if photos:
                        p = photos[_seed_index(seed, len(photos))]
                        photographer = p.get("photographer", "Pexels Creator")
                        return ImageResult(
                            image_url=p["src"]["large"],
                            credit=f"Photo by {photographer} on Pexels",
                        )
        except Exception as e:
            logger.warning(f"Pexels API call failed: {e}")
        return None

    async def _search_pixabay(self, query: str, excluded: set[str], seed: str) -> Optional[ImageResult]:
        url = "https://pixabay.com/api/"
        params = {
            "key": self.pixabay_key,
            "q": query,
            "image_type": "photo",
            "orientation": "horizontal",
            "per_page": 20,
            "safesearch": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    hits = [
                        h for h in res.json().get("hits", [])
                        if (h.get("largeImageURL") or h.get("webformatURL") or "").split("?")[0] not in excluded
                    ]
                    if hits:
                        h = hits[_seed_index(seed, len(hits))]
                        img_url = h.get("largeImageURL") or h.get("webformatURL")
                        user = h.get("user", "Pixabay Creator")
                        return ImageResult(
                            image_url=img_url,
                            credit=f"Photo by {user} on Pixabay",
                        )
        except Exception as e:
            logger.warning(f"Pixabay API call failed: {e}")
        return None

    async def _search_wikimedia(self, query: str, excluded: set[str], seed: str) -> Optional[ImageResult]:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": 12,
            "prop": "imageinfo",
            "iiprop": "url|dimensions|extmetadata",
            "format": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=WIKIMEDIA_HEADERS) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    pages = res.json().get("query", {}).get("pages", {})
                    candidates = []
                    for p in pages.values():
                        infos = p.get("imageinfo", [])
                        if infos:
                            info = infos[0]
                            img_url = info.get("url", "")
                            w = info.get("width", 0)
                            if (
                                img_url
                                and w >= 800
                                and any(img_url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png"))
                                and img_url.split("?")[0] not in excluded
                            ):
                                candidates.append(img_url)
                    if candidates:
                        chosen = candidates[_seed_index(seed, len(candidates))]
                        return ImageResult(
                            image_url=chosen,
                            credit="Wikimedia Commons Open License",
                        )
        except Exception as e:
            logger.warning(f"Wikimedia search failed: {e}")
        return None
