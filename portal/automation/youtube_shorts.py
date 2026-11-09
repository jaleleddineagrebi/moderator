"""The channel's real, public YouTube Shorts, so each article can link to its companion video.

A YouTube video ID is 11 characters (e.g. `eoLg0CbAPT8`). The moderator's run folder names
(`20261105_141814_youtube_short`) are NOT video IDs and must never be used to build video URLs.

Needs YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID (a `UC...` channel ID or an `@handle`). Without them, or if
YouTube cannot be reached, articles are still published, just without a companion video.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger("YouTubeShorts")

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
API = "https://www.googleapis.com/youtube/v3"


def is_youtube_id(value: Any) -> bool:
    return isinstance(value, str) and bool(YOUTUBE_ID.fullmatch(value))


def short_record(video_id: str, snippet: dict[str, Any]) -> dict[str, Any]:
    """Row for the portal's YouTubeShort table, with URLs derived from the real video ID."""
    title = (snippet.get("title") or "YouTube Short").strip()
    lines = [ln.strip() for ln in (snippet.get("description") or "").splitlines() if ln.strip()]
    return {
        "id": video_id,
        "title": title,
        "youtubeUrl": f"https://www.youtube.com/shorts/{video_id}",
        "embedUrl": f"https://www.youtube.com/embed/{video_id}",
        "topic": title,
        "hookAngle": lines[0] if lines else None,
        "publishedAt": snippet.get("publishedAt"),
    }


def pick_unused(shorts: list[dict[str, Any]], used_ids: set[str], count: int) -> list[dict[str, Any]]:
    """The newest `count` Shorts that no earlier article has used (input is newest first)."""
    return [s for s in shorts if is_youtube_id(s.get("id")) and s["id"] not in used_ids][:count]


async def fetch_channel_shorts(limit: int = 25) -> list[dict[str, Any]]:
    """Newest-first list of public, embeddable uploads of the channel. Never raises."""
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    channel = os.getenv("YOUTUBE_CHANNEL_ID", "").strip()
    if not key or not channel:
        logger.warning("YOUTUBE_API_KEY / YOUTUBE_CHANNEL_ID not set: articles will be published without a companion Short")
        return []
    headers = {"x-goog-api-key": key}
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            if channel.startswith("@"):
                res = await client.get(f"{API}/channels", params={"part": "id", "forHandle": channel})
                res.raise_for_status()
                items = res.json().get("items") or []
                if not items:
                    logger.warning(f"YouTube channel handle {channel} not found")
                    return []
                channel = items[0]["id"]
            if not channel.startswith("UC"):
                logger.warning("YOUTUBE_CHANNEL_ID must be a channel ID starting with UC (or an @handle)")
                return []
            uploads = "UU" + channel[2:]  # a channel's uploads playlist
            res = await client.get(f"{API}/playlistItems", params={
                "part": "contentDetails", "playlistId": uploads, "maxResults": min(limit, 50)})
            res.raise_for_status()
            ids = [i["contentDetails"]["videoId"] for i in res.json().get("items", [])
                   if is_youtube_id(i.get("contentDetails", {}).get("videoId"))]
            if not ids:
                return []
            res = await client.get(f"{API}/videos", params={"part": "snippet,status", "id": ",".join(ids)})
            res.raise_for_status()
            by_id = {v["id"]: v for v in res.json().get("items", [])}
    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning(f"Could not list the channel's Shorts ({type(e).__name__}: {e}); publishing without a companion Short")
        return []
    shorts = []
    for vid in ids:  # playlist order = newest first
        video = by_id.get(vid)
        status = (video or {}).get("status") or {}
        if video and status.get("privacyStatus") == "public" and status.get("embeddable", True):
            shorts.append(short_record(vid, video.get("snippet") or {}))
    logger.info(f"Found {len(shorts)} public, embeddable Short(s) on the channel")
    return shorts
