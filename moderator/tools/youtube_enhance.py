"""Optional extras for a freshly uploaded long video: add it to a "Deep Dives" playlist and upload its captions.

These calls need a broader YouTube scope than the upload-only token (which is kept narrow on purpose so a leaked
GitHub secret cannot edit the channel). So they only run when a *manage* token is available:
  - the GitHub secret YOUTUBE_MANAGE_TOKEN, or
  - the local file tokens/youtube_manage.json (created by `optimize-channel`).
Without one this module does nothing and says so; the upload itself is never affected.

YouTube has no API for pinned comments or end screens: set those once in YouTube Studio (end-screen templates
can be saved and reused for every video)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .. import ROOT

MANAGE_SCOPE = "https://www.googleapis.com/auth/youtube"
FORCE_SSL_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
DEFAULT_PLAYLIST = "Deep Dives"


def manage_credentials() -> Credentials | None:
    """Credentials with the `youtube` scope, or None when no manage token is configured."""
    sources: list[str] = []
    env = os.environ.get("YOUTUBE_MANAGE_TOKEN", "").strip()
    if env:
        sources.append(env)
    local = ROOT / "tokens" / "youtube_manage.json"
    if local.exists():
        sources.append(local.read_text(encoding="utf-8"))
    for raw in sources:
        try:
            info = json.loads(raw)
            scopes = info.get("scopes") or []
            if MANAGE_SCOPE not in scopes and FORCE_SSL_SCOPE not in scopes:
                continue
            creds = Credentials.from_authorized_user_info(info, scopes)
            if not creds.valid:
                creds.refresh(Request())
            return creds
        except Exception:  # noqa: BLE001 - an unusable token just means "no extras"
            continue
    return None


def find_or_create_playlist(yt, title: str) -> str:
    """Return the id of the user's playlist called `title`, creating a public one when missing."""
    page = None
    while True:
        resp = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page).execute()
        for item in resp.get("items", []):
            if item["snippet"]["title"].strip().lower() == title.strip().lower():
                return item["id"]
        page = resp.get("nextPageToken")
        if not page:
            break
    created = yt.playlists().insert(
        part="snippet,status",
        body={"snippet": {"title": title, "description": "Long-form deep dives on psychology, AI, the body and money."},
              "status": {"privacyStatus": "public"}},
    ).execute()
    return created["id"]


def enhance_long_video(video_id: str, lang: str, captions: Path | None, playlist_title: str | None = None) -> dict[str, str]:
    """Playlist + captions for an uploaded long video. Returns a short status per step; never raises."""
    creds = manage_credentials()
    if creds is None:
        return {"extras": "skipped (no manage token: set the YOUTUBE_MANAGE_TOKEN secret to enable playlist and captions)"}
    out: dict[str, str] = {}
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:  # noqa: BLE001
        return {"extras": f"skipped ({e})"}

    title = playlist_title or os.environ.get("YOUTUBE_LONG_PLAYLIST") or DEFAULT_PLAYLIST
    try:
        playlist_id = find_or_create_playlist(yt, title)
        yt.playlistItems().insert(
            part="snippet",
            body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
        ).execute()
        out["playlist"] = f"added to '{title}'"
    except Exception as e:  # noqa: BLE001
        out["playlist"] = f"not added: {e}"

    if captions and captions.exists():
        try:
            yt.captions().insert(
                part="snippet",
                body={"snippet": {"videoId": video_id, "language": lang, "name": "Captions", "isDraft": False}},
                media_body=MediaFileUpload(str(captions), mimetype="application/octet-stream"),
            ).execute()
            out["captions"] = "uploaded"
        except Exception as e:  # noqa: BLE001
            out["captions"] = f"not uploaded: {e}"
    return out
