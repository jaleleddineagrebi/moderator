"""Which of our own videos get views? Public YouTube Data API numbers only (needs YOUTUBE_API_KEY, free).

Used by the weekly `channel-report` workflow and as evidence for the long-video idea research.
CTR and average view duration are private to the channel owner (YouTube Analytics API, different OAuth scope),
so this report sticks to views, likes, comments and age."""

from __future__ import annotations

import os
import re
import statistics
from datetime import datetime, timezone

import httpx

API = "https://www.googleapis.com/youtube/v3"
DEFAULT_CHANNEL_ID = "UCzjz2ArvjE4RgR_2k2o53mg"  # public channel id (same one the portal footer links to)
SHORT_MAX_SECONDS = 70  # our Shorts are under 60 s; our long videos are well above this


def available() -> bool:
    return bool(os.environ.get("YOUTUBE_API_KEY"))


def parse_duration(iso: str) -> int:
    """ISO 8601 duration such as PT4M32S -> seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def classify(title: str, seconds: int) -> str:
    return "short" if seconds < SHORT_MAX_SECONDS or "#shorts" in title.lower() else "long"


def _age_days(published: str, now: datetime) -> float:
    return max(1.0, (now - datetime.fromisoformat(published.replace("Z", "+00:00"))).total_seconds() / 86400)


def summarize(videos: list[dict], now: datetime | None = None) -> dict:
    """videos: [{id, title, published, seconds, views, likes, comments}] -> per-format statistics."""
    now = now or datetime.now(timezone.utc)
    out: dict[str, dict] = {}
    for fmt in ("short", "long"):
        rows = []
        for v in videos:
            if classify(v["title"], v["seconds"]) != fmt:
                continue
            age = _age_days(v["published"], now)
            rows.append({**v, "format": fmt, "age_days": round(age, 1), "views_per_day": round(v["views"] / age, 1)})
        rows.sort(key=lambda r: r["views"], reverse=True)
        views = [r["views"] for r in rows]
        out[fmt] = {
            "count": len(rows),
            "total_views": sum(views),
            "median_views": int(statistics.median(views)) if views else 0,
            "zero_view_videos": sum(1 for x in views if x <= 5),
            "top": rows[:5],
            "bottom": rows[-5:][::-1] if len(rows) > 5 else [],
            "avg_seconds": int(sum(r["seconds"] for r in rows) / len(rows)) if rows else 0,
        }
    return out


def render_markdown(stats: dict, channel: str = "") -> str:
    lines = [f"## Channel report{f' - {channel}' if channel else ''}", ""]
    for fmt, label in (("short", "Shorts"), ("long", "Long videos")):
        s = stats[fmt]
        lines += [f"### {label}: {s['count']} videos", ""]
        if not s["count"]:
            lines += ["No videos yet.", ""]
            continue
        lines += [
            f"- Total views: **{s['total_views']}**, median per video: **{s['median_views']}**, average length {s['avg_seconds']} s",
            f"- Videos with 5 views or fewer: {s['zero_view_videos']}",
            "",
            "Best:", "",
        ]
        lines += [f"- {r['views']} views ({r['views_per_day']}/day), {r['seconds']} s - [{r['title']}](https://youtube.com/watch?v={r['id']})" for r in s["top"]]
        if s["bottom"]:
            lines += ["", "Weakest:", ""]
            lines += [f"- {r['views']} views, {r['seconds']} s - {r['title']}" for r in s["bottom"]]
        lines.append("")
    return "\n".join(lines)


async def fetch_videos(channel_id: str | None = None, limit: int = 200) -> tuple[str, list[dict]]:
    """Latest uploads of the channel with their statistics. Public data only."""
    key = os.environ["YOUTUBE_API_KEY"]
    channel_id = channel_id or os.environ.get("YOUTUBE_CHANNEL_ID") or DEFAULT_CHANNEL_ID
    async with httpx.AsyncClient(timeout=30, headers={"x-goog-api-key": key}) as client:
        r = await client.get(f"{API}/channels", params={"part": "contentDetails,snippet", "id": channel_id})
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            raise RuntimeError(f"channel {channel_id} not found")
        uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        name = items[0]["snippet"]["title"]
        ids: list[str] = []
        page = None
        while len(ids) < limit:
            params = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
            if page:
                params["pageToken"] = page
            r = await client.get(f"{API}/playlistItems", params=params)
            r.raise_for_status()
            body = r.json()
            ids += [i["contentDetails"]["videoId"] for i in body.get("items", [])]
            page = body.get("nextPageToken")
            if not page:
                break
        videos: list[dict] = []
        for k in range(0, len(ids[:limit]), 50):
            r = await client.get(f"{API}/videos", params={"part": "snippet,statistics,contentDetails", "id": ",".join(ids[k:k + 50])})
            r.raise_for_status()
            for v in r.json().get("items", []):
                st = v.get("statistics", {})
                videos.append({
                    "id": v["id"], "title": v["snippet"]["title"], "published": v["snippet"]["publishedAt"],
                    "seconds": parse_duration(v["contentDetails"]["duration"]),
                    "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
                })
    return name, videos


async def own_best(fmt: str = "long", limit: int = 5) -> list[dict]:
    """Our own best videos of a format, as compact evidence for idea research. [] when unavailable."""
    if not available():
        return []
    _, videos = await fetch_videos()
    rows = summarize(videos)[fmt]["top"][:limit]
    return [{"title": r["title"], "views": r["views"], "views_per_day": r["views_per_day"], "seconds": r["seconds"]} for r in rows]
