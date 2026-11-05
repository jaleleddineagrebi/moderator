"""TikTok publishing through the Content Posting API (https://developers.tiktok.com/doc/content-posting-api-get-started).

Two modes:
- draft  (scope video.upload): the video lands in your TikTok inbox; you add sounds/caption and post from the app.
         Works before TikTok audits your app, for public accounts too. The default.
- direct (scope video.publish): posted straight away with the caption. Until TikTok audits the app, direct posts
         must be SELF_ONLY (private) and the account must be private.

Credentials (never committed; tokens/ is git-ignored):
- client key/secret of your TikTok developer app: env TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET,
  or tokens/tiktok_client.json written by `moderator tiktok-auth`
- user token: env TIKTOK_TOKEN (JSON) or tokens/tiktok.json. TikTok rotates the refresh token on every refresh,
  so the newest token is always written back to tokens/tiktok.json (CI copies it back into the TIKTOK_TOKEN secret).
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from pathlib import Path

import httpx

from .youtube_upload import TOKENS_DIR

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
TOKEN_URL = f"{API}/oauth/token/"
SCOPES = ["user.info.basic", "video.upload", "video.publish"]
TOKEN_PATH = TOKENS_DIR / "tiktok.json"
CLIENT_PATH = TOKENS_DIR / "tiktok_client.json"
DEFAULT_PORT = 3455  # register http://127.0.0.1:3455/callback/ (or port *) as a redirect URI of the app
MAX_SINGLE_CHUNK = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024
PRIVACY = {"private": "SELF_ONLY", "friends": "MUTUAL_FOLLOW_FRIENDS", "followers": "FOLLOWER_OF_CREATOR",
           "public": "PUBLIC_TO_EVERYONE"}
DONE = {"PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"}


class TikTokError(RuntimeError):
    pass


def _client() -> tuple[str, str]:
    key, secret = os.environ.get("TIKTOK_CLIENT_KEY"), os.environ.get("TIKTOK_CLIENT_SECRET")
    if not (key and secret) and CLIENT_PATH.exists():
        saved = json.loads(CLIENT_PATH.read_text(encoding="utf-8"))
        key, secret = key or saved.get("client_key"), secret or saved.get("client_secret")
    if not (key and secret):
        raise TikTokError("TikTok app credentials missing: set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET "
                          "or run `python -m moderator tiktok-auth --client-key ... --client-secret ...`")
    return key, secret


def pkce_pair() -> tuple[str, str]:
    """TikTok's desktop Login Kit uses the hex-encoded SHA-256 of the verifier as the S256 challenge."""
    verifier = secrets.token_urlsafe(64)[:96]
    return verifier, hashlib.sha256(verifier.encode()).hexdigest()


def _token_request(data: dict) -> dict:
    resp = httpx.post(TOKEN_URL, data=data, timeout=30,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    body = resp.json() if resp.content else {}
    if resp.status_code != 200 or "access_token" not in body:
        raise TikTokError(f"TikTok token request failed ({resp.status_code}): "
                          f"{body.get('error')} {body.get('error_description', '')}".strip())
    now = int(time.time())
    return {"access_token": body["access_token"], "refresh_token": body["refresh_token"],
            "open_id": body.get("open_id"), "scope": body.get("scope", ""),
            "expires_at": now + int(body.get("expires_in", 0)),
            "refresh_expires_at": now + int(body.get("refresh_expires_in", 0))}


def save_token(token: dict, path: Path = TOKEN_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, indent=2), encoding="utf-8")
    return path


def load_token(path: Path = TOKEN_PATH) -> dict:
    raw = os.environ.get("TIKTOK_TOKEN") or (path.read_text(encoding="utf-8") if path.exists() else "")
    if not raw:
        raise TikTokError("No TikTok token: run `python -m moderator tiktok-auth` (or set the TIKTOK_TOKEN secret)")
    return json.loads(raw)


def fresh_token(path: Path = TOKEN_PATH) -> dict:
    """Access tokens last 2 hours; refresh (and save the rotated refresh token) when close to expiry."""
    token = load_token(path)
    if token.get("expires_at", 0) - 300 > time.time():
        return token
    if token.get("refresh_expires_at") and token["refresh_expires_at"] < time.time():
        raise TikTokError("TikTok refresh token expired (they last 180 days): run `moderator tiktok-auth` again")
    key, secret = _client()
    new = _token_request({"client_key": key, "client_secret": secret, "grant_type": "refresh_token",
                          "refresh_token": token["refresh_token"]})
    save_token(new, path)
    return new


def authorize(client_key: str, client_secret: str, port: int = DEFAULT_PORT, scopes: list[str] | None = None) -> dict:
    """Desktop OAuth with PKCE: opens the browser, waits for TikTok to redirect to 127.0.0.1:<port>/callback/."""
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    CLIENT_PATH.write_text(json.dumps({"client_key": client_key, "client_secret": client_secret}), encoding="utf-8")
    redirect_uri = f"http://127.0.0.1:{port}/callback/"
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_key": client_key, "scope": ",".join(scopes or SCOPES), "response_type": "code",
        "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
    result: dict = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in query.items()})
            ok = "code" in result and result.get("state") == state
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(("TikTok connected. You can close this tab." if ok
                              else f"TikTok login failed: {result.get('error_description') or result.get('error') or 'state mismatch'}").encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), Callback)
    print(f"Opening the browser for TikTok login. If it does not open, visit:\n{url}")
    webbrowser.open(url)
    server.timeout = 300
    server.handle_request()
    server.server_close()
    if result.get("state") != state or "code" not in result:
        raise TikTokError(f"TikTok login failed: {result.get('error_description') or result.get('error') or 'no code / state mismatch'}")
    token = _token_request({"client_key": client_key, "client_secret": client_secret, "code": result["code"],
                            "grant_type": "authorization_code", "redirect_uri": redirect_uri,
                            "code_verifier": verifier})
    save_token(token)
    return token


def _api(token: dict, path: str, payload: dict) -> dict:
    resp = httpx.post(f"{API}{path}", json=payload, timeout=60,
                      headers={"Authorization": f"Bearer {token['access_token']}",
                               "Content-Type": "application/json; charset=UTF-8"})
    body = resp.json() if resp.content else {}
    err = body.get("error") or {}
    if resp.status_code != 200 or err.get("code") not in (None, "ok"):
        raise TikTokError(f"TikTok {path} failed ({resp.status_code}): {err.get('code')} {err.get('message', '')}".strip())
    return body.get("data") or {}


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count): one chunk up to 64 MB, else 10 MB chunks with the remainder in the last."""
    if size <= MAX_SINGLE_CHUNK:
        return size, 1
    return CHUNK, size // CHUNK


def upload(video: Path, caption: str, *, mode: str = "draft", privacy: str = "private", ai_generated: bool = False,
           token_path: Path = TOKEN_PATH, wait_s: int = 180) -> dict:
    """Upload one MP4. Returns {mode, publish_id, status, privacy, post_ids}."""
    if mode not in ("draft", "direct"):
        raise ValueError("mode must be draft or direct")
    token = fresh_token(token_path)
    size = video.stat().st_size
    chunk_size, count = chunk_plan(size)
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk_size, "total_chunk_count": count}
    level = PRIVACY.get(privacy, privacy)
    if mode == "direct":
        info = _api(token, "/post/publish/creator_info/query/", {})
        options = info.get("privacy_level_options") or []
        if level not in options:
            raise TikTokError(f"privacy '{privacy}' is not allowed for this account now (allowed: {options}). "
                              "Unaudited apps can only post SELF_ONLY to a private account; use --mode draft instead.")
        post_info = {"title": caption[:2200], "privacy_level": level,
                     "disable_comment": bool(info.get("comment_disabled")),
                     "disable_duet": bool(info.get("duet_disabled")),
                     "disable_stitch": bool(info.get("stitch_disabled")),
                     "video_cover_timestamp_ms": 1000, "is_aigc": ai_generated}
        data = _api(token, "/post/publish/video/init/", {"post_info": post_info, "source_info": source})
    else:
        data = _api(token, "/post/publish/inbox/video/init/", {"source_info": source})
    publish_id, upload_url = data["publish_id"], data["upload_url"]

    with video.open("rb") as f:
        for i in range(count):
            start = i * chunk_size
            length = size - start if i == count - 1 else chunk_size
            f.seek(start)
            resp = httpx.put(upload_url, content=f.read(length), timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(length),
                "Content-Range": f"bytes {start}-{start + length - 1}/{size}"})
            if resp.status_code not in (200, 201, 206):
                raise TikTokError(f"TikTok upload of chunk {i + 1}/{count} failed ({resp.status_code}): {resp.text[:300]}")

    status: dict = {}
    deadline = time.time() + wait_s
    while time.time() < deadline:
        status = _api(token, "/post/publish/status/fetch/", {"publish_id": publish_id})
        if status.get("status") in DONE or status.get("status") == "FAILED":
            break
        time.sleep(5)
    if status.get("status") == "FAILED":
        raise TikTokError(f"TikTok rejected the video: {status.get('fail_reason')}")
    return {"mode": mode, "publish_id": publish_id, "status": status.get("status", "PROCESSING"),
            "privacy": level if mode == "direct" else "draft (finish in the TikTok app inbox)",
            "post_ids": status.get("publicaly_available_post_id") or []}
