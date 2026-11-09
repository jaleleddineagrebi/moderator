"""Portal daily pipeline: real companion Shorts, saving to the database, and the pull request workflow."""

import asyncio
import json

import httpx
import pytest
import yaml

from moderator import ROOT
from portal.automation import pipeline as pipeline_mod
from portal.automation import youtube_shorts as ys

REAL_ID = "eoLg0CbAPT8"


def test_run_folder_names_are_not_youtube_ids():
    assert ys.is_youtube_id(REAL_ID) and ys.is_youtube_id("dPKT_k9MiZM")
    assert not ys.is_youtube_id("20261102_171413_youtube_short")  # what the old code used as a video ID
    assert not ys.is_youtube_id("short") and not ys.is_youtube_id(None) and not ys.is_youtube_id("abc def ghi")


def test_pick_unused_skips_used_and_invalid_ids():
    shorts = [{"id": "20261102_171413_youtube_short"}, {"id": REAL_ID}, {"id": "dPKT_k9MiZM"}, {"id": "sB7HGFvGbZE"}]
    assert [s["id"] for s in ys.pick_unused(shorts, {REAL_ID}, count=2)] == ["dPKT_k9MiZM", "sB7HGFvGbZE"]


def _youtube_transport(requests):
    def handler(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("/channels"):
            assert request.url.params["forHandle"] == "@mychannel"
            return httpx.Response(200, json={"items": [{"id": "UCabcdefghijklmnopqrstuv"}]})
        if path.endswith("/playlistItems"):
            assert request.url.params["playlistId"] == "UUabcdefghijklmnopqrstuv"  # the uploads playlist
            ids = [REAL_ID, "dPKT_k9MiZM", "sB7HGFvGbZE"]
            return httpx.Response(200, json={"items": [{"contentDetails": {"videoId": i}} for i in ids]})
        videos = {
            REAL_ID: {"status": {"privacyStatus": "public", "embeddable": True},
                      "snippet": {"title": "You Like It", "description": "Ever replayed it?\nmore",
                                  "publishedAt": "2026-11-04T10:00:00Z"}},
            "dPKT_k9MiZM": {"status": {"privacyStatus": "unlisted", "embeddable": True}, "snippet": {"title": "Hidden"}},
            "sB7HGFvGbZE": {"status": {"privacyStatus": "public", "embeddable": False}, "snippet": {"title": "No embed"}},
        }
        return httpx.Response(200, json={"items": [{"id": k, **v} for k, v in videos.items()]})

    return httpx.MockTransport(handler)


def test_fetch_channel_shorts_returns_only_public_embeddable_videos_with_real_urls(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "key")
    monkeypatch.setenv("YOUTUBE_CHANNEL_ID", "@mychannel")
    requests = []
    real = httpx.AsyncClient
    monkeypatch.setattr(ys.httpx, "AsyncClient", lambda **kw: real(transport=_youtube_transport(requests), **kw))
    shorts = asyncio.run(ys.fetch_channel_shorts())
    assert [s["id"] for s in shorts] == [REAL_ID]
    assert shorts[0]["youtubeUrl"] == f"https://www.youtube.com/shorts/{REAL_ID}"
    assert shorts[0]["embedUrl"] == f"https://www.youtube.com/embed/{REAL_ID}"
    assert shorts[0]["hookAngle"] == "Ever replayed it?"
    assert all(r.headers["x-goog-api-key"] == "key" and "key=" not in str(r.url) for r in requests)  # never in the URL


def test_fetch_channel_shorts_without_config_or_on_error_returns_empty_list(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert asyncio.run(ys.fetch_channel_shorts()) == []
    monkeypatch.setenv("YOUTUBE_API_KEY", "key")
    monkeypatch.setenv("YOUTUBE_CHANNEL_ID", "UCabcdefghijklmnopqrstuv")
    real = httpx.AsyncClient
    monkeypatch.setattr(ys.httpx, "AsyncClient", lambda **kw: real(
        transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"error": "quota"})), **kw))
    assert asyncio.run(ys.fetch_channel_shorts()) == []  # articles still publish, without a Short


def _fake_post(slug, short=None):
    return {"slug": slug, "title": f"Title {slug}", "contentMarkdown": "x", "coverImageUrl": "https://img",
            "youtubeShortId": short["id"] if short else None, "youtubeShort": short}


@pytest.fixture
def daily(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline_mod, "DAILY_POSTS_DIR", tmp_path / "daily_posts")
    monkeypatch.setattr(pipeline_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_output"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "gh_summary"))

    async def no_sleep(_):
        return None

    monkeypatch.setattr(pipeline_mod.asyncio, "sleep", no_sleep)
    pipe = pipeline_mod.DailyContentPipeline()

    async def fake_refs():
        return [ys.short_record(REAL_ID, {"title": "You Like It", "description": "Q?"}),
                ys.short_record("dPKT_k9MiZM", {"title": "Second"})]

    async def fake_generate(slot, matched_short, recent_titles):
        return _fake_post(slot.split()[0].lower(), matched_short)

    monkeypatch.setattr(pipe, "get_existing_video_cross_references", fake_refs)
    monkeypatch.setattr(pipe, "generate_post", fake_generate)
    return pipe, tmp_path


def _api(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: real(transport=httpx.MockTransport(handler), timeout=kw.get("timeout")))


def test_daily_run_saves_to_database_archives_and_reports(daily, monkeypatch):
    pipe, tmp = daily
    monkeypatch.setenv("PORTAL_API_ENDPOINT", "https://portal.example/")
    monkeypatch.setenv("INTERNAL_API_SECRET", "s3cret")
    sent = []

    def handler(request):
        sent.append((str(request.url), request.headers["authorization"], json.loads(request.content)))
        return httpx.Response(201, json={"ok": True})

    _api(monkeypatch, handler)
    posts = asyncio.run(pipe.run_daily())
    assert len(posts) == 2
    assert [u for u, _, _ in sent] == ["https://portal.example/api/posts"] * 2
    assert all(auth == "Bearer s3cret" for _, auth, _ in sent)
    assert sent[0][2]["youtubeShort"]["id"] == REAL_ID  # the Short travels with the post, so the API creates it first
    files = list((tmp / "daily_posts").glob("*.json"))
    assert len(files) == 1 and len(json.loads(files[0].read_text(encoding="utf-8"))) == 2
    out = (tmp / "gh_output").read_text(encoding="utf-8")
    assert f"posts_file=daily_posts/{files[0].name}" in out and "posts_titles=Title morning | Title evening" in out
    summary = (tmp / "gh_summary").read_text(encoding="utf-8")
    assert f"https://www.youtube.com/shorts/{REAL_ID}" in summary and "saved" in summary


def test_daily_run_fails_loudly_when_database_save_fails(daily, monkeypatch):
    pipe, tmp = daily
    monkeypatch.setenv("PORTAL_API_ENDPOINT", "https://portal.example")
    monkeypatch.setenv("INTERNAL_API_SECRET", "s3cret")
    statuses = []

    def handler(request):
        # first post: 500 twice (one retry); second post: 401 (bad secret, never retried)
        status = 500 if len(statuses) < 2 else 401
        statuses.append(status)
        return httpx.Response(status, text="Failed to create post")

    _api(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="NOT saved to the database"):
        asyncio.run(pipe.run_daily())
    assert statuses == [500, 500, 401]
    assert list((tmp / "daily_posts").glob("*.json"))  # still archived, so the pull request has the posts
    assert "FAILED" in (tmp / "gh_summary").read_text(encoding="utf-8")


def test_daily_run_without_portal_secrets_is_an_error_not_a_silent_skip(daily, monkeypatch):
    pipe, tmp = daily
    monkeypatch.delenv("PORTAL_API_ENDPOINT", raising=False)
    monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="NOT saved to the database"):
        asyncio.run(pipe.run_daily())
    assert list((tmp / "daily_posts").glob("*.json"))


def test_used_short_ids_come_from_archives(daily):
    pipe, tmp = daily
    d = tmp / "daily_posts"
    d.mkdir()
    (d / "2026-11-05_0800.json").write_text(json.dumps([
        {"youtubeShortId": REAL_ID}, {"youtubeShortId": "20261102_171413_youtube_short"}, {"youtubeShortId": None}]),
        encoding="utf-8")
    assert pipe.get_used_short_ids() == {REAL_ID}


def test_daily_workflow_opens_a_pr_and_starts_ci_for_the_required_check():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "daily-portal-content.yml").read_text(encoding="utf-8"))
    assert wf["permissions"]["pull-requests"] == "write" and wf["permissions"]["actions"] == "write"
    steps = {s.get("name"): s for s in wf["jobs"]["crawl-synthesize-publish"]["steps"]}
    pr = steps["Open a pull request with the new posts"]
    assert "always()" in pr["if"] and "posts_file" in pr["if"]
    assert "gh pr create" in pr["run"] and "gh workflow run ci.yml" in pr["run"]
    assert "origin main" not in pr["run"]  # never pushes to main
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert "workflow_dispatch" in ci[True]  # YAML parses the key `on` as True
