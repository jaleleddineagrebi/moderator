import hashlib
import json
import time
from pathlib import Path

import httpx
import pytest
import yaml

from moderator import ROOT
from moderator.tools import tiktok_upload as tt


class FakeResp:
    def __init__(self, status: int, body: dict | None = None):
        self.status_code = status
        self._body = body or {}
        self.content = json.dumps(self._body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


def _token(path: Path, expires_in: int = 3600) -> None:
    path.write_text(json.dumps({"access_token": "old-access", "refresh_token": "old-refresh", "open_id": "u1",
                                "scope": "video.upload,video.publish", "expires_at": int(time.time()) + expires_in,
                                "refresh_expires_at": int(time.time()) + 86400}), encoding="utf-8")


def test_pkce_is_hex_sha256_and_chunk_plan():
    verifier, challenge = tt.pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert challenge == hashlib.sha256(verifier.encode()).hexdigest()
    assert tt.chunk_plan(30_000_000) == (30_000_000, 1)  # one chunk up to 64 MB
    assert tt.chunk_plan(100 * 1024 * 1024) == (tt.CHUNK, 10)  # remainder goes into the last chunk


def test_draft_upload_refreshes_rotated_token_and_sends_chunks(tmp_path, monkeypatch):
    token_path = tmp_path / "tiktok.json"
    _token(token_path, expires_in=10)  # about to expire: must refresh first
    monkeypatch.delenv("TIKTOK_TOKEN", raising=False)
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "ck")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "cs")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        if url == tt.TOKEN_URL:
            assert kw["data"]["grant_type"] == "refresh_token" and kw["data"]["refresh_token"] == "old-refresh"
            return FakeResp(200, {"access_token": "new-access", "refresh_token": "new-refresh", "open_id": "u1",
                                  "scope": "video.upload", "expires_in": 7200, "refresh_expires_in": 15552000})
        assert kw["headers"]["Authorization"] == "Bearer new-access"
        if url.endswith("/inbox/video/init/"):
            assert kw["json"]["source_info"] == {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000,
                                                 "total_chunk_count": 1}
            return FakeResp(200, {"data": {"publish_id": "p1", "upload_url": "https://upload.example/u"},
                                  "error": {"code": "ok"}})
        if url.endswith("/status/fetch/"):
            return FakeResp(200, {"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok"}})
        raise AssertionError(url)

    puts = []
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "put", lambda url, **kw: puts.append(kw["headers"]) or FakeResp(201))
    res = tt.upload(video, "caption #fyp", mode="draft", token_path=token_path)
    assert res["status"] == "SEND_TO_USER_INBOX" and res["publish_id"] == "p1"
    assert puts == [{"Content-Type": "video/mp4", "Content-Length": "1000", "Content-Range": "bytes 0-999/1000"}]
    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "new-refresh"  # rotated token written back


def test_direct_upload_refuses_privacy_the_account_cannot_use(tmp_path, monkeypatch):
    token_path = tmp_path / "tiktok.json"
    _token(token_path)
    monkeypatch.delenv("TIKTOK_TOKEN", raising=False)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 10)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResp(
        200, {"data": {"privacy_level_options": ["SELF_ONLY"]}, "error": {"code": "ok"}}))
    with pytest.raises(tt.TikTokError, match="draft"):
        tt.upload(video, "c", mode="direct", privacy="public", token_path=token_path)


def test_api_error_is_reported(tmp_path, monkeypatch):
    token_path = tmp_path / "tiktok.json"
    _token(token_path)
    monkeypatch.delenv("TIKTOK_TOKEN", raising=False)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResp(
        403, {"error": {"code": "unaudited_client_can_only_post_to_private_accounts", "message": "no"}}))
    with pytest.raises(tt.TikTokError, match="unaudited_client"):
        tt.upload(video, "c", mode="draft", token_path=token_path)


def test_tiktok_workflow_is_owner_gated_and_separate():
    raw = (ROOT / ".github" / "workflows" / "tiktok-upload.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(raw)
    job = wf["jobs"]["tiktok"]
    assert "startsWith(github.event.comment.body, '/tiktok')" in job["if"]
    assert "github.repository_owner" in job["if"] and "COLLABORATOR" in job["if"]
    assert wf["permissions"]["contents"] == "read"
    steps = {s.get("name"): s for s in job["steps"]}
    assert "COMMENT" not in steps["Send to TikTok"]["run"]  # comment text never reaches the shell command line
    assert "claude" not in raw.lower()


def test_tiktok_publish_records_approval_caption_and_ai_flag(tmp_path, monkeypatch):
    from moderator import publish
    from moderator.engine.registry import Registry
    from moderator.engine.state import StateStore, new_state

    registry = Registry(ROOT, {})
    wf = registry.workflow("youtube_short")
    run_dir = tmp_path / "run"
    state = new_state("run", wf, {"languages": ["en"]}, {s.agent: registry.specs[s.agent].public() for s in wf.steps})
    for step in state["steps"].values():
        step["status"] = "done"
    state["steps"]["qa"]["status"] = "waiting_for_approval"
    state["steps"]["qa"]["outputs"] = {"video_en": "final_short_en.mp4"}
    state["steps"]["packaging"]["outputs"] = {"metadata": "metadata.json"}
    state["steps"]["visuals"]["outputs"] = {"licenses": "assets/licenses.json"}
    state["checkpoints"]["C"]["status"] = "pending"
    store = StateStore.create(run_dir, state)
    (run_dir / "final_short_en.mp4").write_bytes(b"mp4")
    (run_dir / "assets").mkdir()
    (run_dir / "assets/licenses.json").write_text(json.dumps([{"scene": "scene_01", "provider": "nano_banana"}]), encoding="utf-8")
    (run_dir / "metadata.json").write_text(json.dumps({"en": {"title": "T", "description": "Q?", "hashtags": ["#Shorts"],
                                                              "tags": [], "tiktok_caption": "T\nQ?\n\n#fyp"}}), encoding="utf-8")
    seen = {}

    def fake_upload(video, caption, *, mode, privacy, ai_generated):
        seen.update(video=video, caption=caption, mode=mode, ai=ai_generated)
        return {"mode": mode, "publish_id": "p9", "status": "SEND_TO_USER_INBOX", "privacy": "draft", "post_ids": []}

    monkeypatch.setattr(tt, "upload", fake_upload)
    res = publish.approve_and_upload_tiktok(store, "github:owner")
    assert res[0]["publish_id"] == "p9" and seen["caption"] == "T\nQ?\n\n#fyp" and seen["ai"] is True
    assert store.data["checkpoints"]["C"]["status"] == "approved"
    assert (run_dir / "tiktok_uploads.json").is_file()
