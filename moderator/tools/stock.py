"""Free stock media: Pexels and Pixabay (both allow free commercial use without attribution).
Each search result carries the license info that QA later checks."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

TIMEOUT = httpx.Timeout(30, read=120)


def available() -> dict[str, bool]:
    return {"pexels": bool(os.environ.get("PEXELS_API_KEY")), "pixabay": bool(os.environ.get("PIXABAY_API_KEY"))}


async def search_videos(query: str, provider: str, min_seconds: float = 4) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        if provider == "pexels":
            r = await client.get("https://api.pexels.com/videos/search",
                                 params={"query": query, "orientation": "portrait", "per_page": 15},
                                 headers={"Authorization": os.environ["PEXELS_API_KEY"]})
            r.raise_for_status()
            results = []
            for v in r.json().get("videos", []):
                files = [f for f in v["video_files"] if f.get("height") and f["height"] >= 1280 and f.get("file_type") == "video/mp4"]
                if not files or v["duration"] < min_seconds:
                    continue
                best = min(files, key=lambda f: f["height"])  # smallest file that is still HD
                results.append({"url": best["link"], "page": v["url"], "author": v["user"]["name"], "provider": "pexels",
                                "license": "Pexels License (free commercial use, no attribution required)",
                                "portrait": v["height"] >= v["width"], "duration": v["duration"]})
            return sorted(results, key=lambda x: not x["portrait"])
        if provider == "pixabay":
            r = await client.get("https://pixabay.com/api/videos/",
                                 params={"key": os.environ["PIXABAY_API_KEY"], "q": query[:100], "per_page": 15, "safesearch": "true"})
            r.raise_for_status()
            results = []
            for v in r.json().get("hits", []):
                size = v["videos"].get("large") or v["videos"].get("medium")
                if not size or not size.get("url") or v["duration"] < min_seconds:
                    continue
                results.append({"url": size["url"], "page": v["pageURL"], "author": v["user"], "provider": "pixabay",
                                "license": "Pixabay Content License (free commercial use, no attribution required)",
                                "portrait": size["height"] >= size["width"], "duration": v["duration"]})
            return sorted(results, key=lambda x: not x["portrait"])
    raise ValueError(f"unknown provider {provider}")


async def search_photos(query: str, provider: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        if provider == "pexels":
            r = await client.get("https://api.pexels.com/v1/search",
                                 params={"query": query, "orientation": "portrait", "per_page": 10},
                                 headers={"Authorization": os.environ["PEXELS_API_KEY"]})
            r.raise_for_status()
            return [{"url": p["src"]["large2x"], "page": p["url"], "author": p["photographer"], "provider": "pexels",
                     "license": "Pexels License (free commercial use, no attribution required)"} for p in r.json().get("photos", [])]
        if provider == "pixabay":
            r = await client.get("https://pixabay.com/api/",
                                 params={"key": os.environ["PIXABAY_API_KEY"], "q": query[:100], "orientation": "vertical",
                                         "per_page": 10, "safesearch": "true", "image_type": "photo"})
            r.raise_for_status()
            return [{"url": p["largeImageURL"], "page": p["pageURL"], "author": p["user"], "provider": "pixabay",
                     "license": "Pixabay Content License (free commercial use, no attribution required)"} for p in r.json().get("hits", [])]
    raise ValueError(f"unknown provider {provider}")


async def download(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
