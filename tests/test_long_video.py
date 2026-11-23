"""Long-video improvements: real chapters and captions, channel report, optional playlist/captions step."""

from datetime import datetime, timezone

from moderator.tools import channel_stats, long_video, youtube_enhance


def _timing(starts_and_ends):
    return [{"scene": f"scene_{i:02d}", "start": a, "end": b, "words": []} for i, (a, b) in enumerate(starts_and_ends, 1)]


def test_fmt_clock():
    assert long_video.fmt_clock(0) == "0:00"
    assert long_video.fmt_clock(65.9) == "1:05"
    assert long_video.fmt_clock(3725) == "1:02:05"


def test_chapters_come_from_real_scene_starts():
    scenes = [{"id": f"scene_{i:02d}", "chapter": c} for i, c in enumerate(["Intro", "", "Why it happens", "", "The surprise", ""], 1)]
    timing = _timing([(0, 14), (14, 30), (30, 52), (52, 70), (70, 95), (95, 110)])
    assert long_video.chapter_lines(scenes, timing) == ["0:00 Intro", "0:30 Why it happens", "1:10 The surprise"]


def test_first_chapter_is_forced_to_zero_and_invalid_sets_are_dropped():
    scenes = [{"id": "scene_01", "chapter": ""}, {"id": "scene_02", "chapter": "A"}, {"id": "scene_03", "chapter": "B"}, {"id": "scene_04", "chapter": "C"}]
    timing = _timing([(0, 12), (12, 40), (40, 80), (80, 120)])
    assert long_video.chapter_lines(scenes, timing)[0].startswith("0:00 ")
    # fewer than 3 chapters: YouTube would ignore the list, so we do not write one
    assert long_video.chapter_lines(scenes[:3], _timing([(0, 12), (12, 40), (40, 80)])) == []
    # a chapter shorter than 10 s invalidates the list
    short = _timing([(0, 12), (12, 20), (20, 26), (26, 120)])
    assert long_video.chapter_lines(scenes, short) == []
    assert long_video.chapter_lines([{"id": "scene_01"}], _timing([(0, 5)])) == []


def test_srt_cues_follow_word_timings():
    words = [{"start": i * 0.4, "end": i * 0.4 + 0.35, "text": f"w{i}"} for i in range(12)]
    srt = long_video.build_srt([{"scene": "scene_01", "start": 0, "end": 5, "words": words}], max_words=5)
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == 3
    assert blocks[0].startswith("1\n00:00:00,000 --> ")
    assert "w0 w1 w2 w3 w4" in blocks[0]
    assert long_video.srt_time(3725.5) == "01:02:05,500"


def test_channel_stats_duration_classification_and_summary():
    assert channel_stats.parse_duration("PT4M32S") == 272
    assert channel_stats.parse_duration("PT45S") == 45
    assert channel_stats.parse_duration("PT1H2M3S") == 3723
    assert channel_stats.classify("A trick #shorts", 200) == "short"
    assert channel_stats.classify("Why we sleep", 45) == "short"
    assert channel_stats.classify("Why we sleep", 280) == "long"
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    videos = [
        {"id": "a", "title": "Long one", "published": "2026-11-10T00:00:00Z", "seconds": 280, "views": 100, "likes": 3, "comments": 0},
        {"id": "b", "title": "Short one", "published": "2026-11-18T00:00:00Z", "seconds": 40, "views": 5000, "likes": 90, "comments": 4},
        {"id": "c", "title": "Long two", "published": "2026-10-01T00:00:00Z", "seconds": 300, "views": 2, "likes": 0, "comments": 0},
    ]
    stats = channel_stats.summarize(videos, now)
    assert stats["short"]["count"] == 1 and stats["long"]["count"] == 2
    assert stats["long"]["zero_view_videos"] == 1
    assert stats["long"]["top"][0]["id"] == "a" and stats["long"]["top"][0]["views_per_day"] == 10.0
    md = channel_stats.render_markdown(stats, "Test")
    assert "Long videos: 2 videos" in md and "Shorts: 1 videos" in md


def test_playlist_and_captions_are_skipped_without_a_manage_token(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_enhance, "ROOT", tmp_path)  # no tokens/youtube_manage.json here
    monkeypatch.delenv("YOUTUBE_MANAGE_TOKEN", raising=False)
    out = youtube_enhance.enhance_long_video("abc12345678", "en", None)
    assert list(out) == ["extras"] and "skipped" in out["extras"]


def test_upload_only_token_is_not_accepted_as_manage_token(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_enhance, "ROOT", tmp_path)
    narrow = ('{"token":"x","refresh_token":"r","client_id":"i","client_secret":"s","token_uri":"https://oauth2.googleapis.com/token",'
              '"scopes":["https://www.googleapis.com/auth/youtube.upload"]}')
    monkeypatch.setenv("YOUTUBE_MANAGE_TOKEN", narrow)
    assert youtube_enhance.manage_credentials() is None


def test_long_script_schema_and_workflow_wiring():
    from agents.scriptwriter.handler import LONG_BUDGET_SECONDS, make_schema
    from moderator import ROOT
    from moderator.engine.registry import Registry
    schema = make_schema(["en"], is_long=True)
    scenes = schema["properties"]["scenes"]
    assert scenes["minItems"] >= 18 and "chapter" in scenes["items"]["required"]
    assert "chapter" not in make_schema(["en"])["properties"]["scenes"]["items"]["required"]
    assert LONG_BUDGET_SECONDS[0] >= 240
    wf = Registry(ROOT, {}).workflow("youtube_long")
    packaging = next(s for s in wf.steps if s.id == "packaging")
    assert "audio" in packaging.depends_on  # chapters and captions need the voiceover timings


def test_long_workflow_end_to_end_with_real_chapters_captions_and_search_evidence(tmp_path, monkeypatch):
    """Whole youtube_long run with fake LLM / ffmpeg: research evidence, story prompt, chapters, SRT, QA."""
    import asyncio
    import json
    from pathlib import Path

    from PIL import Image

    from moderator import ROOT
    from moderator.engine import llm as llm_mod
    from moderator.engine.orchestrator import Orchestrator
    from moderator.engine.registry import Registry
    from moderator.engine.state import StateStore, new_state
    from moderator.tools import ffmpeg, history as hist_mod, stock, tts as tts_mod, youtube

    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(hist_mod, "PATH", tmp_path / "topics.jsonl")
    monkeypatch.setattr(stock, "available", lambda: {"pexels": False, "pixabay": False})

    async def fake_suggestions(query, language="en", limit=10):
        return ["why do we dream", "why do we dream every night"]

    monkeypatch.setattr(youtube, "search_suggestions", fake_suggestions)
    prompts: dict[str, str] = {}
    chapter_titles = {1: "Intro", 5: "Why it happens", 9: "The hidden trigger", 13: "What science says", 17: "What to do"}

    class FakeGemini:
        def __init__(self, ctx, cfg):
            self.ctx = ctx

        async def ask(self, prompt, *, system=None, schema=None, tools=None, model=None, complexity=None, images=None):
            props = (schema or {}).get("properties", {})
            if "ideas" in props:
                prompts["research"] = prompt
                return {"ideas": [{"id": f"idea_{k}", "title": f"Why We Dream {k}", "angle": "What dreams do for memory.",
                                   "hook": {"en": "Your brain edits your day every night."}, "keywords": ["dreams"],
                                   "reason": "Search demand", "sources": ["https://example.com"]} for k in range(1, 4)]}
            if "scenes" in props:
                prompts["script"] = prompt
                words = " ".join(["word"] * 34) + "."
                scenes = [{"vo": {"en": words}, "on_screen": {"en": f"BEAT {i}"}, "chapter": chapter_titles.get(i, ""),
                           "visual": {"description": f"scene {i}", "search_terms": [f"term {i}"], "prefer": "photo" if i % 3 == 0 else "video"}}
                          for i in range(1, 21)]
                return {"title": "Why We Dream", "scenes": scenes}
            if "en" in props:
                return {"en": {"title": "Why We Dream: The Real Reason", "description": "Dreams explained.",
                               "hashtags": ["#Psychology"], "tags": ["dreams"], "thumbnail_text": "WHY DREAM"}}
            if "issues" in props:
                return {"issues": []}
            if "violations" in props:
                return {"violations": []}
            return ""

        async def generate_image(self, prompt, dest, *, aspect_ratio="9:16", size=(1080, 1920), model=None):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", size or (1920, 1080), (30, 50, 90)).save(dest)
            return "fake-image-model"

    monkeypatch.setattr(llm_mod, "create_llm", lambda ctx, cfg: FakeGemini(ctx, cfg))

    async def fake_still(src, dst, cwd, seconds=8, zoom_in=True, size=None):
        Path(dst).write_bytes(b"fake-mp4")

    async def fake_frame(src, dst, cwd, at=1.0):
        Image.new("RGB", (960, 540), (40, 60, 90)).save(dst)

    async def fake_run(args, cwd, timeout=900):
        out = Path(cwd) / args[-1]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-media-output")
        return ""

    async def fake_duration(path):
        return 280.0 if "voiceover" in str(path) else 13.0

    async def fake_probe(path):
        return {"format": {"duration": "290"}, "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
            {"codec_type": "audio", "codec_name": "aac"}]}

    async def fake_loudness(path, cwd):
        return {"lufs": -14.1, "true_peak_db": -1.4}

    async def fake_synth(txt, voice, out, rate="+0%"):
        Path(out).write_bytes(b"fake-mp3")
        return []

    monkeypatch.setattr(ffmpeg, "still_to_clip", fake_still)
    monkeypatch.setattr(ffmpeg, "frame_at", fake_frame)
    monkeypatch.setattr(ffmpeg, "run", fake_run)
    monkeypatch.setattr(ffmpeg, "duration", fake_duration)
    monkeypatch.setattr(ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(ffmpeg, "loudness", fake_loudness)
    monkeypatch.setattr(tts_mod, "synthesize", fake_synth)

    registry = Registry(ROOT, {})
    wf = registry.workflow("youtube_long")
    wf.settings["retry_backoff_s"] = 0.0
    params = {**wf.params, "niche": "Psychology", "languages": ["en"], "auto_approve": ["A", "B"]}
    agents = {s.agent: registry.specs[s.agent].public() for s in wf.steps}
    run_dir = tmp_path / "runs" / "long_test"
    store = StateStore.create(run_dir, new_state("long_test", wf, params, agents))
    outcome = asyncio.run(asyncio.wait_for(Orchestrator(store, wf, registry).run(headless=True), 60))

    assert outcome == "waiting", store.data["steps"]
    assert "WHAT PEOPLE TYPE INTO YOUTUBE SEARCH" in prompts["research"] and "why do we dream" in prompts["research"]
    assert "COLD OPEN" in prompts["script"] and "chapter" in prompts["script"]
    meta = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))["en"]
    assert "Chapters:" in meta["description"] and meta["description"].count("\n0:00 Intro") == 1
    assert meta["chapters"][1].endswith("Why it happens")
    srt = (run_dir / "captions_en.srt").read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:00,") and " --> " in srt
    qa = json.loads((run_dir / "qa_report.json").read_text(encoding="utf-8"))
    assert qa["passed"] is True, qa
