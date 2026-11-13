"""YouTube uploads through the official Data API (OAuth).

Supports either:
- One shared channel token: env `YOUTUBE_TOKEN` or `tokens/youtube.json`
- One token per language channel: env `YOUTUBE_TOKEN_<LANG>` or `tokens/youtube_<lang>.json`

Uploading costs 1,600 of the 10,000 daily quota units per video.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .. import ROOT

UPLOAD_SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
# Full channel management (edit/delete videos, branding). Only `optimize-channel` uses it, with its own
# local token file; the upload token (also the GitHub secret) keeps UPLOAD_SCOPES so a leak cannot wreck the channel.
MANAGE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TOKENS_DIR = ROOT / "tokens"
MANAGE_TOKEN = TOKENS_DIR / "youtube_manage.json"
EDUCATION_CATEGORY = "27"


def authorize(client_secret: Path, lang: str | None = None, scopes: list[str] | None = None,
              path: Path | None = None) -> tuple[Path, str]:
    """Opens the browser: sign in and pick the YouTube channel (brand account or main channel).
    Defaults to upload-only scopes; pass MANAGE_SCOPES (and MANAGE_TOKEN) for channel management."""
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes or UPLOAD_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    TOKENS_DIR.mkdir(exist_ok=True)
    path = path or TOKENS_DIR / (f"youtube_{lang.lower()}.json" if lang else "youtube.json")
    path.write_text(creds.to_json(), encoding="utf-8")
    return path, channel_title(creds)


def credentials_from_file(path: Path) -> Credentials:
    info = json.loads(path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(info, info.get("scopes") or UPLOAD_SCOPES)
    if not creds.valid:
        creds.refresh(Request())
    return creds


def credentials(lang: str) -> Credentials:
    candidates: list[tuple[str, str]] = []
    for env_name in (f"YOUTUBE_TOKEN_{lang.upper()}", "YOUTUBE_TOKEN"):
        val = os.environ.get(env_name)
        if val and val.strip():
            candidates.append((env_name, val))
    for path in (TOKENS_DIR / f"youtube_{lang.lower()}.json", TOKENS_DIR / "youtube.json", MANAGE_TOKEN):
        if path.exists():
            candidates.append((str(path.relative_to(ROOT)), path.read_text(encoding="utf-8")))

    if not candidates:
        raise RuntimeError(
            f"No YouTube token found for '{lang}' (checked YOUTUBE_TOKEN_{lang.upper()}, YOUTUBE_TOKEN, "
            f"tokens/youtube_{lang.lower()}.json, tokens/youtube.json). "
            f"Run: python -m moderator youtube-auth --client-secret client_secret.json"
        )

    last_err: Exception | None = None
    for source_name, raw in candidates:
        try:
            info = json.loads(raw)
            granted_scopes = info.get("scopes") or UPLOAD_SCOPES
            creds = Credentials.from_authorized_user_info(info, granted_scopes)
            if not creds.valid:
                creds.refresh(Request())
            return creds
        except Exception as err:  # noqa: BLE001
            last_err = err
            continue

    raise RuntimeError(
        f"YouTube OAuth refresh token is expired or revoked ({last_err}).\n"
        "Why this happens: Google Cloud OAuth apps in 'Testing' mode expire refresh tokens after 7 days.\n"
        "How to fix permanently:\n"
        "  1. Open Google Cloud Console -> APIs & Services -> OAuth consent screen -> click 'PUBLISH APP' (moves from Testing to In production so tokens never expire).\n"
        "  2. Regenerate your token locally: uv run python -m moderator youtube-auth --client-secret client_secret.json\n"
        "  3. Copy the contents of tokens/youtube.json into your GitHub Actions secret YOUTUBE_TOKEN."
    ) from last_err


def channel_title(creds: Credentials) -> str:
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    return items[0]["snippet"]["title"] if items else "(no channel on this account)"


def upload(lang: str, video: Path, meta: dict, privacy: str, thumbnail: Path | None = None) -> dict:
    creds = credentials(lang)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    tags, size = [], 0
    for tag in meta.get("tags", []):  # YouTube caps the tag list at 500 characters
        size += len(tag) + 3
        if size > 480:
            break
        tags.append(tag)
    is_long = str(meta.get("format") or "short").lower() == "long"
    raw_title = meta["title"].strip()
    if not is_long and "#shorts" not in raw_title.lower() and len(raw_title) <= 91:
        raw_title = f"{raw_title} #shorts"
    body = {
        "snippet": {
            "title": raw_title[:100],
            "description": f"{meta['description']}\n\n{' '.join(meta.get('hashtags', []))}"[:4900],
            "tags": tags,
            "categoryId": EDUCATION_CATEGORY,
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    request = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 << 20, resumable=True))
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_url = f"https://youtube.com/watch?v={response['id']}" if is_long else f"https://youtube.com/shorts/{response['id']}"
    result = {"id": response["id"], "url": video_url,
              "privacy": response["status"]["privacyStatus"], "channel": channel_title(creds)}
    if thumbnail and thumbnail.exists():
        result["thumbnail"] = set_thumbnail(yt, response["id"], thumbnail)
    return result


def set_thumbnail(yt, video_id: str, thumbnail: Path) -> str:
    """Upload a custom thumbnail for an existing YouTube video ID."""
    try:  # needs a phone-verified channel; Shorts feeds may still show a frame instead
        yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail))).execute()
        return "set"
    except Exception as e:  # noqa: BLE001 - the video is already up; a thumbnail failure is not fatal
        msg = str(e)
        if "doesn't have permissions to upload and set custom video thumbnails" in msg or "forbidden" in msg.lower():
            return (
                "not set (channel needs 1-time SMS verification: YouTube Studio -> Settings -> Channel -> "
                "Feature eligibility -> Intermediate features -> Verify phone number)"
            )
        return f"not set: {e}"
