"""TikTok uploads through the official Content Posting API (OAuth 2.0 + PKCE, FILE_UPLOAD source).

Tokens (one JSON blob per account):
- one shared account: env `TIKTOK_TOKEN` or `tokens/tiktok.json`
- one per language:   env `TIKTOK_TOKEN_<LANG>` or `tokens/tiktok_<lang>.json`
The app credentials come from env `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET`.

Until TikTok audits the app, every post is forced to private (`SELF_ONLY`) by TikTok itself.
Scopes needed: user.info.basic, video.upload, video.publish.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import httpx

from .. import ROOT

API = "https://open.tiktokapis.com"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPES = ["user.info.basic", "video.upload", "video.publish"]
TOKENS_DIR = ROOT / "tokens"
PRIVACY_MAP = {"private": "SELF_ONLY", "unlisted": "FOLLOWER_OF_CREATOR", "public": "PUBLIC_TO_EVERYONE"}
MAX_CAPTION = 2200
MAX_SINGLE_CHUNK = 64 << 20  # files up to 64 MB go in one chunk


class TikTokError(RuntimeError):
    pass


def app_credentials() -> tuple[str, str]:
    key, secret = os.environ.get("TIKTOK_CLIENT_KEY"), os.environ.get("TIKTOK_CLIENT_SECRET")
    if not key or not secret:
        raise TikTokError("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET (TikTok developer portal -> your app).")
    return key, secret


def _check(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        raise TikTokError(f"HTTP {resp.status_code}: {resp.text[:300]}") from None
    err = body.get("error")
    if isinstance(err, dict) and err.get("code") not in (None, "ok"):
        raise TikTokError(f"{err.get('code')}: {err.get('message')} (log_id {err.get('log_id')})")
    if "error" in body and isinstance(err, str):  # OAuth endpoints use a flat error shape
        raise TikTokError(f"{err}: {body.get('error_description')}")
    if resp.status_code >= 400:
        raise TikTokError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return body


# --- authorization (run once, locally) -------------------------------------------------------

def new_pkce() -> tuple[str, str]:
    """TikTok wants the code_challenge as the HEX sha256 of the verifier (not base64url)."""
    verifier = secrets.token_urlsafe(64)[:96]
    return verifier, hashlib.sha256(verifier.encode()).hexdigest()


def authorize_url(client_key: str, redirect_uri: str, challenge: str, state: str) -> str:
    q = {"client_key": client_key, "scope": ",".join(SCOPES), "response_type": "code",
         "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    return f"{AUTH_URL}?{urlencode(q)}"


def extract_code(pasted: str) -> str:
    """Accepts the full redirected URL or just the code value."""
    pasted = pasted.strip()
    if "code=" in pasted:
        qs = parse_qs(urlparse(pasted).query)
        if "code" in qs:
            return qs["code"][0]
    return unquote(pasted)


def exchange_code(code: str, redirect_uri: str, verifier: str, client: httpx.Client | None = None) -> dict:
    key, secret = app_credentials()
    c = client or httpx.Client(timeout=30)
    data = _check(c.post(f"{API}/v2/oauth/token/", data={
        "client_key": key, "client_secret": secret, "code": code, "grant_type": "authorization_code",
        "redirect_uri": redirect_uri, "code_verifier": verifier}))
    data["obtained_at"] = int(time.time())
    return data


def authorize(redirect_uri: str, lang: str | None = None, ask=input, say=print) -> Path:
    """Manual flow: open the URL, log in as the TikTok account, paste back the address you were redirected to."""
    key, _ = app_credentials()
    verifier, challenge = new_pkce()
    state = secrets.token_urlsafe(12)
    say("Open this URL in a browser, log in with the TikTok account that will publish, and approve:\n")
    say(authorize_url(key, redirect_uri, challenge, state))
    say("\nAfter approving you land on your redirect page (it may show an error/404, that is fine).")
    say("Copy the FULL address from the browser bar and paste it here.")
    pasted = ask("Redirected URL (or the code): ")
    if "state=" in pasted and parse_qs(urlparse(pasted.strip()).query).get("state", [state])[0] != state:
        raise TikTokError("state mismatch: restart the authorization")
    token = exchange_code(extract_code(pasted), redirect_uri, verifier)
    TOKENS_DIR.mkdir(exist_ok=True)
    path = TOKENS_DIR / (f"tiktok_{lang.lower()}.json" if lang else "tiktok.json")
    path.write_text(json.dumps(token, indent=2), encoding="utf-8")
    return path


# --- token loading / refresh -------------------------------------------------------------------

def _raw_token(lang: str) -> str:
    raw = os.environ.get(f"TIKTOK_TOKEN_{lang.upper()}") or os.environ.get("TIKTOK_TOKEN")
    for p in (TOKENS_DIR / f"tiktok_{lang.lower()}.json", TOKENS_DIR / "tiktok.json"):
        if not raw and p.exists():
            raw = p.read_text(encoding="utf-8")
    if not raw:
        raise TikTokError(f"No TikTok token for '{lang}' (TIKTOK_TOKEN_{lang.upper()}, TIKTOK_TOKEN, "
                          f"tokens/tiktok.json). Run: python -m moderator tiktok-auth --redirect-uri <your registered URI>")
    return raw


def access_token(lang: str, client: httpx.Client | None = None, now=time.time) -> str:
    """Returns a valid access token, refreshing when it is (nearly) expired."""
    info = json.loads(_raw_token(lang))
    age = now() - info.get("obtained_at", 0)
    if info.get("access_token") and age < info.get("expires_in", 0) - 300:
        return info["access_token"]
    key, secret = app_credentials()
    c = client or httpx.Client(timeout=30)
    new = _check(c.post(f"{API}/v2/oauth/token/", data={
        "client_key": key, "client_secret": secret, "grant_type": "refresh_token",
        "refresh_token": info["refresh_token"]}))
    if new.get("refresh_token") and new["refresh_token"] != info["refresh_token"]:
        print("::warning::TikTok rotated the refresh token. Re-run tiktok-auth and update the TIKTOK_TOKEN secret "
              "before the old one expires." if os.environ.get("GITHUB_ACTIONS") else
              "TikTok rotated the refresh token; saving the new one to tokens/tiktok.json.")
        if not os.environ.get("GITHUB_ACTIONS"):
            new["obtained_at"] = int(now())
            TOKENS_DIR.mkdir(exist_ok=True)
            (TOKENS_DIR / "tiktok.json").write_text(json.dumps(new, indent=2), encoding="utf-8")
    return new["access_token"]


# --- posting ----------------------------------------------------------------------------------

def build_caption(meta: dict) -> str:
    tags = " ".join(meta.get("hashtags", []))
    text = f"{meta['title'].strip()}\n{tags}".strip()
    return text[:MAX_CAPTION]


def pick_privacy(requested: str, options: list[str]) -> str:
    want = PRIVACY_MAP.get(requested, "SELF_ONLY")
    return want if want in options else "SELF_ONLY"


def upload(lang: str, video: Path, meta: dict, privacy: str, client: httpx.Client | None = None,
           poll_s: float = 5.0, timeout_s: float = 300.0, sleep=time.sleep) -> dict:
    token = access_token(lang, client)
    c = client or httpx.Client(timeout=120)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}

    info = _check(c.post(f"{API}/v2/post/publish/creator_info/query/", headers=headers)).get("data", {})
    chosen = pick_privacy(privacy, info.get("privacy_level_options") or ["SELF_ONLY"])

    size = video.stat().st_size
    if size > MAX_SINGLE_CHUNK:
        raise TikTokError(f"{video.name} is {size >> 20} MB; chunked upload above 64 MB is not implemented")
    init = _check(c.post(f"{API}/v2/post/publish/video/init/", headers=headers, json={
        "post_info": {"title": build_caption(meta), "privacy_level": chosen, "disable_duet": False,
                      "disable_comment": False, "disable_stitch": False},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1},
    }))["data"]

    put = c.put(init["upload_url"], content=video.read_bytes(), headers={
        "Content-Type": "video/mp4", "Content-Length": str(size),
        "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if put.status_code not in (200, 201, 206):
        raise TikTokError(f"video upload failed: HTTP {put.status_code} {put.text[:200]}")

    deadline = time.monotonic() + timeout_s
    status = {}
    while time.monotonic() < deadline:
        status = _check(c.post(f"{API}/v2/post/publish/status/fetch/", headers=headers,
                               json={"publish_id": init["publish_id"]})).get("data", {})
        if status.get("status") == "FAILED":
            raise TikTokError(f"TikTok rejected the post: {status.get('fail_reason')}")
        if status.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            break
        sleep(poll_s)
    else:
        raise TikTokError(f"timed out waiting for TikTok (last status: {status.get('status')})")
    return {"publish_id": init["publish_id"], "status": status["status"], "privacy": chosen,
            "post_ids": status.get("publicaly_available_post_id", [])}
