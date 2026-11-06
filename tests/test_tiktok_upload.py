"""Tests for the TikTok Content Posting API client, using httpx.MockTransport (offline)."""

import json
import time
from pathlib import Path

import httpx
import pytest

from moderator.tools import tiktok_upload as tt


def _fresh_token(**kw):
    return json.dumps({"access_token": "AT", "refresh_token": "RT", "expires_in": 86400,
                       "obtained_at": int(time.time()), **kw})


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "ck")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "cs")
    monkeypatch.setenv("TIKTOK_TOKEN", _fresh_token())
    monkeypatch.setattr(tt, "TOKENS_DIR", tmp_path / "tokens")


def test_pkce_challenge_is_hex_sha256():
    verifier, challenge = tt.new_pkce()
    assert 43 <= len(verifier) <= 128
    assert len(challenge) == 64 and int(challenge, 16) >= 0


def test_extract_code_from_url_or_raw():
    assert tt.extract_code("https://x.io/cb?code=abc%2Adef&state=s&scopes=a") == "abc*def"
    assert tt.extract_code("abc%2Adef") == "abc*def"


def test_pick_privacy_falls_back_to_private():
    assert tt.pick_privacy("public", ["SELF_ONLY"]) == "SELF_ONLY"
    assert tt.pick_privacy("public", ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]) == "PUBLIC_TO_EVERYONE"


def test_caption_is_capped():
    caption = tt.build_caption({"title": "Why You Forget Everything", "hashtags": ["#Shorts", "#Psychology"]})
    assert "daily brain bias check" in caption
    assert "#Shorts" in caption

    caption_fr = tt.build_caption({"title": "Pourquoi ton cerveau ment", "hashtags": ["#Shorts"]}, lang="fr")
    assert "check-up mental" in caption_fr

    assert len(tt.build_caption({"title": "t" * 3000, "hashtags": ["#a"]})) == tt.MAX_CAPTION


def test_expired_token_is_refreshed(monkeypatch):
    monkeypatch.setenv("TIKTOK_TOKEN", _fresh_token(obtained_at=0))
    seen = {}

    def handler(req):
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"access_token": "NEW", "refresh_token": "RT"})

    assert tt.access_token("en", httpx.Client(transport=httpx.MockTransport(handler))) == "NEW"
    assert "grant_type=refresh_token" in seen["body"]


def test_api_error_is_raised():
    def handler(req):
        return httpx.Response(200, json={"error": {"code": "access_token_invalid", "message": "bad", "log_id": "1"}})

    with pytest.raises(tt.TikTokError, match="access_token_invalid"):
        tt.upload("en", Path(__file__), {"title": "t"}, "private",
                  httpx.Client(transport=httpx.MockTransport(handler)))


def test_full_upload_flow(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 1000)
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.url.path.endswith("creator_info/query/"):
            return httpx.Response(200, json={"data": {"privacy_level_options": ["SELF_ONLY"]}, "error": {"code": "ok"}})
        if req.url.path.endswith("video/init/"):
            body = json.loads(req.content)
            assert body["post_info"]["privacy_level"] == "SELF_ONLY"  # public requested, not allowed -> private
            assert body["source_info"] == {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000,
                                           "total_chunk_count": 1}
            return httpx.Response(200, json={"data": {"publish_id": "P1", "upload_url": "https://up.example/u"},
                                             "error": {"code": "ok"}})
        if req.url.host == "up.example":
            assert req.headers["Content-Range"] == "bytes 0-999/1000"
            return httpx.Response(201)
        return httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}})

    res = tt.upload("en", video, {"title": "Hi", "hashtags": ["#x"]}, "public",
                    httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    assert res["publish_id"] == "P1" and res["status"] == "PUBLISH_COMPLETE" and res["privacy"] == "SELF_ONLY"
    assert [m for m, _ in calls] == ["POST", "POST", "PUT", "POST"]
