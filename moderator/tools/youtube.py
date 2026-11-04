"""Read-only YouTube Data API v3 lookups (free key, 10,000 quota units/day; a search costs 100).
Used as evidence for niche and trend research. Nothing here uploads anything."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx

API = "https://www.googleapis.com/youtube/v3"


def available() -> bool:
    return bool(os.environ.get("YOUTUBE_API_KEY"))


async def top_recent_shorts(query: str, language: str, days: int = 30, limit: int = 10) -> list[dict]:
    """Most viewed short videos for a query over the last `days`, with view counts."""
    key = os.environ["YOUTUBE_API_KEY"]
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # key in a header, not the URL, so it never shows up in error messages
    async with httpx.AsyncClient(timeout=30, headers={"x-goog-api-key": key}) as client:
        r = await client.get(f"{API}/search", params={
            "part": "snippet", "q": query, "type": "video", "videoDuration": "short",
            "order": "viewCount", "publishedAfter": after, "relevanceLanguage": language, "maxResults": limit,
        })
        r.raise_for_status()
        items = r.json().get("items", [])
        ids = [i["id"]["videoId"] for i in items]
        if not ids:
            return []
        r = await client.get(f"{API}/videos", params={"part": "statistics,snippet", "id": ",".join(ids)})
        r.raise_for_status()
        return [{
            "title": v["snippet"]["title"],
            "channel": v["snippet"]["channelTitle"],
            "published": v["snippet"]["publishedAt"][:10],
            "views": int(v["statistics"].get("viewCount", 0)),
            "url": f"https://www.youtube.com/shorts/{v['id']}",
        } for v in r.json().get("items", [])]
