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
    raw = os.environ.get(f"YOUTUBE_TOKEN_{lang.upper()}") or os.environ.get("YOUTUBE_TOKEN")
    lang_path = TOKENS_DIR / f"youtube_{lang.lower()}.json"
    shared_path = TOKENS_DIR / "youtube.json"
    if not raw and lang_path.exists():
        raw = lang_path.read_text(encoding="utf-8")
    if not raw and shared_path.exists():
        raw = shared_path.read_text(encoding="utf-8")
    if not raw:
        raise RuntimeError(
            f"No YouTube token found for '{lang}' (checked YOUTUBE_TOKEN_{lang.upper()}, YOUTUBE_TOKEN, "
            f"tokens/youtube_{lang.lower()}.json, tokens/youtube.json). "
            f"Run: python -m moderator youtube-auth --client-secret client_secret.json"
        )
    info = json.loads(raw)
    granted_scopes = info.get("scopes") or UPLOAD_SCOPES
    creds = Credentials.from_authorized_user_info(info, granted_scopes)
    if not creds.valid:
        creds.refresh(Request())
    return creds


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
        try:  # needs a phone-verified channel; Shorts feeds may still show a frame instead
            yt.thumbnails().set(videoId=response["id"], media_body=MediaFileUpload(str(thumbnail))).execute()
            result["thumbnail"] = "set"
        except Exception as e:  # noqa: BLE001 - the video is already up; a thumbnail failure is not fatal
            result["thumbnail"] = f"not set: {e}"
    return result
