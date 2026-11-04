"""Free stock media: Pexels, Pixabay, and zero-key Wikimedia Commons (CC0 / Public Domain).
Each search result carries the license info that QA later checks."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

TIMEOUT = httpx.Timeout(30, read=120)
HEADERS = {"User-Agent": "ModeratorShortsBot/0.1 (+https://github.com/jaleleddineagrebi/moderator)"}
# Clips that look bad behind narration: keyed backgrounds, cartoons, screen captures
BAD_TAGS = ("green screen", "greenscreen", "chroma", "animation", "cartoon", "screen recording", "screenshot",
            "text", "code", "loop", "abstract background")


def available() -> dict[str, bool]:
    return {
        "pexels": bool(os.environ.get("PEXELS_API_KEY")),
        "pixabay": bool(os.environ.get("PIXABAY_API_KEY")),
        "wikimedia": os.environ.get("MODERATOR_DISABLE_WIKIMEDIA", "").lower() not in ("1", "true", "yes"),
    }


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _commons_pd_or_cc0_license(extmeta: dict) -> str | None:
    short = _strip_html((extmeta.get("LicenseShortName") or {}).get("value", ""))
    usage = _strip_html((extmeta.get("UsageTerms") or {}).get("value", ""))
    short_low = short.lower()
    combined = f"{short_low} | {usage.lower()}"
    if "by" in short_low or "nc" in short_low or "nd" in short_low:
        return None
    if (
        "cc0" in combined
        or "cc-zero" in combined
        or "creative commons zero" in combined
        or "public domain" in combined
        or short_low.startswith("pd")
    ):
        label = short or usage or "CC0 / Public Domain"
        return f"Wikimedia Commons — {label} (free commercial use, no attribution required)"
    return None


def _pick_pexels_mp4(video_files: list[dict]) -> dict | None:
    mp4s = [
        f for f in video_files
        if f.get("file_type") == "video/mp4"
        and f.get("link")
        and (max(f.get("width") or 0, f.get("height") or 0) >= 1280 or (f.get("height") or 0) >= 720)
    ]
    if not mp4s:
        return None
    # Prefer crisp 1080p-class HD files without downloading oversized 4K masters
    return min(
        mp4s,
        key=lambda f: (
            0 if 1080 <= max(f.get("width") or 0, f.get("height") or 0) <= 2160 else 1,
            abs(max(f.get("width") or 0, f.get("height") or 0) - 1920),
        ),
    )


async def search_videos(query: str, provider: str, min_seconds: float = 3.5) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        if provider == "pexels":
            seen_pages: set[str] = set()
            results: list[dict] = []
            for orientation in ("portrait", None):
                params: dict[str, str | int] = {"query": query, "per_page": 15}
                if orientation:
                    params["orientation"] = orientation
                r = await client.get(
                    "https://api.pexels.com/videos/search",
                    params=params,
                    headers={"Authorization": os.environ["PEXELS_API_KEY"]},
                )
                r.raise_for_status()
                for v in r.json().get("videos", []):
                    if v.get("url") in seen_pages or (v.get("duration") or 0) < min_seconds:
                        continue
                    best = _pick_pexels_mp4(v.get("video_files", []))
                    if not best:
                        continue
                    seen_pages.add(v["url"])
                    results.append({
                        "url": best["link"],
                        "ext": "mp4",
                        "page": v["url"],
                        "author": (v.get("user") or {}).get("name", "Pexels contributor"),
                        "provider": "pexels",
                        "license": "Pexels License (free commercial use, no attribution required)",
                        "portrait": (v.get("height") or 0) >= (v.get("width") or 0),
                        "duration": v["duration"],
                    })
                if len(results) >= 3:
                    break
            return sorted(results, key=lambda x: not x["portrait"])

        if provider == "pixabay":
            seen_pages = set()
            results = []
            for vtype in ("film", "all"):
                r = await client.get(
                    "https://pixabay.com/api/videos/",
                    params={
                        "key": os.environ["PIXABAY_API_KEY"],
                        "q": query[:100],
                        "video_type": vtype,
                        "per_page": 50,
                        "safesearch": "true",
                    },
                )
                r.raise_for_status()
                for v in r.json().get("hits", []):
                    if v.get("pageURL") in seen_pages or (v.get("duration") or 0) < min_seconds:
                        continue
                    if any(t in v.get("tags", "").lower() for t in BAD_TAGS):
                        continue
                    vids = v.get("videos") or {}
                    size = vids.get("large") or vids.get("medium") or vids.get("small")
                    if not size or not size.get("url"):
                        continue
                    if max(size.get("width") or 0, size.get("height") or 0) < 720:
                        continue
                    seen_pages.add(v["pageURL"])
                    results.append({
                        "url": size["url"],
                        "ext": "mp4",
                        "page": v["pageURL"],
                        "tags": v.get("tags", ""),
                        "author": v.get("user", "Pixabay contributor"),
                        "provider": "pixabay",
                        "license": "Pixabay Content License (free commercial use, no attribution required)",
                        "portrait": (size.get("height") or 0) >= (size.get("width") or 0),
                        "duration": v["duration"],
                    })
                if len(results) >= 3:
                    break
            return sorted(results, key=lambda x: not x["portrait"])

        if provider == "wikimedia":
            seen_pages = set()
            results = []
            search_variants = [
                f'filetype:video {query} ("CC0" OR "Public domain")',
                f"filetype:video {query}",
            ]
            for gsr in search_variants:
                r = await client.get(
                    "https://commons.wikimedia.org/w/api.php",
                    params={
                        "action": "query",
                        "generator": "search",
                        "gsrnamespace": "6",
                        "gsrsearch": gsr,
                        "gsrlimit": "25",
                        "prop": "imageinfo",
                        "iiprop": "url|size|mediatype|mime|extmetadata",
                        "format": "json",
                    },
                )
                r.raise_for_status()
                pages = (r.json().get("query") or {}).get("pages") or {}
                for page in pages.values():
                    info = (page.get("imageinfo") or [None])[0]
                    if not info or not info.get("url"):
                        continue
                    page_url = info.get("descriptionurl") or f"https://commons.wikimedia.org/?curid={page.get('pageid')}"
                    if page_url in seen_pages:
                        continue
                    mime = (info.get("mime") or "").lower()
                    size_bytes = int(info.get("size") or 0)
                    dur = float(info.get("duration") or 0)
                    w = int(info.get("width") or 0)
                    h = int(info.get("height") or 0)
                    if not mime.startswith("video/"):
                        continue
                    if not (30_000 <= size_bytes <= 50_000_000):
                        continue
                    if dur and not (min_seconds <= dur <= 180):
                        continue
                    if max(w, h) < 480:
                        continue
                    extmeta = info.get("extmetadata") or {}
                    lic = _commons_pd_or_cc0_license(extmeta)
                    if not lic:
                        continue
                    suffix = Path(urlparse(info["url"]).path).suffix.lower().lstrip(".")
                    ext = suffix if suffix in ("mp4", "webm", "ogv", "mov") else "webm"
                    author = _strip_html((extmeta.get("Artist") or {}).get("value", "")) or "Wikimedia Commons contributor"
                    seen_pages.add(page_url)
                    results.append({
                        "url": info["url"],
                        "ext": ext,
                        "page": page_url,
                        "author": author[:120],
                        "provider": "wikimedia",
                        "license": lic,
                        "portrait": h >= w,
                        "duration": dur or min_seconds,
                        "_res": max(w, h),
                    })
                if len(results) >= 3:
                    break
            results.sort(key=lambda x: (not x["portrait"], -min(x.get("_res", 720), 1920)))
            return results
    raise ValueError(f"unknown provider {provider}")


async def search_photos(query: str, provider: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        if provider == "pexels":
            r = await client.get("https://api.pexels.com/v1/search",
                                 params={"query": query, "orientation": "portrait", "per_page": 10},
                                 headers={"Authorization": os.environ["PEXELS_API_KEY"]})
            r.raise_for_status()
            return [{"url": p["src"]["large2x"], "ext": "jpg", "page": p["url"], "author": p["photographer"], "provider": "pexels", "alt": p.get("alt", ""),
                     "license": "Pexels License (free commercial use, no attribution required)"} for p in r.json().get("photos", [])]
        if provider == "pixabay":
            r = await client.get("https://pixabay.com/api/",
                                 params={"key": os.environ["PIXABAY_API_KEY"], "q": query[:100], "orientation": "vertical",
                                         "per_page": 10, "safesearch": "true", "image_type": "photo"})
            r.raise_for_status()
            return [{"url": p["largeImageURL"], "ext": "jpg", "page": p["pageURL"], "author": p["user"], "provider": "pixabay", "tags": p.get("tags", ""),
                     "license": "Pixabay Content License (free commercial use, no attribution required)"} for p in r.json().get("hits", [])]
    raise ValueError(f"unknown provider {provider}")


async def download(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
