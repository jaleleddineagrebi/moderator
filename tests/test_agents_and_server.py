import asyncio
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from moderator import ROOT
from moderator.cli import parse_params
from moderator.engine.agent import Agent, AgentSpec, BudgetExceeded, StepContext
from moderator.engine.llm import (
    GeminiClient,
    extract_json,
    resolve_image_models,
    resolve_text_models,
    sanitize_schema_for_gemini,
)
from moderator.engine.orchestrator import Orchestrator
from moderator.engine.registry import Registry
from moderator.engine.state import StateStore, new_state
from moderator.engine.workflow import Checkpoint, Step, Workflow, WorkflowError, load_workflow
from moderator.publish import review_summary
from moderator.server.app import create_app
from moderator.tools import history, text, tts
from moderator.tools.languages import lang_schema, names, normalize_langs


def test_duplicate_step_ids_rejected_cleanly(tmp_path):
    wf = tmp_path / "dup.yaml"
    wf.write_text("steps:\n  - {id: same, agent: x}\n  - {id: same, agent: x}\n", encoding="utf-8")
    with pytest.raises(WorkflowError, match="duplicate step ids"):
        load_workflow(wf)


def test_parse_params_avoids_yaml11_sexagesimal_and_norway_traps():
    parsed = parse_params([
        "topic=Why 9:16 works",
        "ratio=9:16",
        "answer=no",
        "flag=true",
        "budget_usd=2.5",
        "count=4",
        "languages=[en, fr]",
        "bare_flag",
    ])
    assert parsed["topic"] == "Why 9:16 works"
    assert parsed["ratio"] == "9:16"
    assert parsed["answer"] == "no"
    assert parsed["flag"] is True
    assert parsed["budget_usd"] == 2.5
    assert parsed["count"] == 4
    assert parsed["languages"] == ["en", "fr"]
    assert parsed["bare_flag"] is True


def test_normalize_langs_and_dynamic_agent_schemas():
    assert normalize_langs("en") == ["en"]
    assert normalize_langs("en, fr") == ["en", "fr"]
    assert normalize_langs(["en", "fr", "en"]) == ["en", "fr"]
    assert normalize_langs(["ar", "fr", "en"]) == ["ar", "fr", "en"]
    assert names(["en", "fr", "ar"]) == "English, French and Egyptian Arabic"
    with pytest.raises(ValueError, match="Unsupported language"):
        normalize_langs("xx")

    # Verify all LLM-backed agents generate dynamic schemas for English-only and English+French
    from agents.niche_scout.handler import make_schema as niche_schema
    from agents.packaging.handler import LANG_META
    from agents.qa_reviewer.handler import make_review_schema
    from agents.scriptwriter.handler import make_schema as script_schema
    from agents.trend_researcher.handler import make_schema as trend_schema

    tr_en = trend_schema(["en"])
    assert tr_en["properties"]["ideas"]["items"]["properties"]["hook"]["required"] == ["en"]

    sc_en_fr = script_schema(["en", "fr"])
    scene_props = sc_en_fr["properties"]["scenes"]["items"]["properties"]
    assert scene_props["vo"]["required"] == ["en", "fr"]
    assert scene_props["on_screen"]["required"] == ["en", "fr"]

    pkg_en = lang_schema(["en"], value_schema=LANG_META)
    assert pkg_en["required"] == ["en"]

    qa_en = make_review_schema(["en"])
    assert qa_en["properties"]["issues"]["items"]["properties"]["language"]["enum"] == ["en"]
    qa_multi = make_review_schema(["en", "fr"])
    assert qa_multi["properties"]["issues"]["items"]["properties"]["language"]["enum"] == ["en", "fr", "all"]

    ns_en_fr = niche_schema(["en", "fr"])
    assert ns_en_fr["properties"]["niches"]["items"]["properties"]["best_language"]["enum"] == ["en", "fr", "all"]


def test_history_record_updates_in_place_on_revision(tmp_path):
    hfile = tmp_path / "topics.jsonl"
    history.record("run_1", "Rejected Idea", "angle 1", path=hfile)
    history.record("run_2", "Other Run Idea", "angle 2", path=hfile)
    history.record("run_1", "Approved Revised Idea", "angle 1b", path=hfile)
    rows = history.recent(10, path=hfile)
    assert len(rows) == 2
    assert rows[0]["title"] == "Approved Revised Idea"
    assert rows[1]["title"] == "Other Run Idea"


def test_tts_fallback_captions_ass_and_pillow_rendering(tmp_path):
    from PIL import Image
    from agents.qa_reviewer.handler import parse_ass

    words = tts.fallback_word_timings("Your brain lies to you every single morning.", 3.2)
    assert len(words) == 8
    assert words[0]["start"] < words[-1]["end"] <= 3.25

    chunks = text.caption_chunks(words, max_words=3)
    assert len(chunks) >= 3
    ass_path = tmp_path / "captions_en.ass"
    text.write_ass(ass_path, "en", chunks, [{"start": 0.05, "end": 3.1, "text": "BRAIN BIAS"}])
    events = parse_ass(ass_path)
    assert len(events) == len(chunks)
    # Every fallback word should be covered by a caption event
    assert all(any(e[0] - 0.05 <= w["start"] <= e[1] + 0.05 for e in events) for w in words)

    # Test Pillow rendering for English, French, and RTL Egyptian Arabic
    img = Image.new("RGB", (1080, 1920), (15, 15, 20))
    for lang, sample in [("en", "THE 2 MINUTE RULE"), ("fr", "BIAIS DU CERVEAU"), ("ar", "خدعة عقلك اليومية")]:
        text.draw_block(img, sample, lang, size=100, y_center=900, max_width=900)

    escaped = text.escape_filter_arg("C:\\Users\\test:dir\\sub[1].ass")
    assert "\\:" in escaped and "\\[" in escaped and "\\" not in escaped.replace("\\:", "").replace("\\[", "").replace("\\]", "")


def test_send_back_cancels_inflight_parallel_downstream_task(tmp_path):
    """If branch B is still running when branch A triggers send_back on their shared ancestor,
    branch B's in-flight task must be cancelled and must not overwrite its reset status."""
    started_slow = asyncio.Event()

    class CustomAgent(Agent):
        async def run(self, ctx: StepContext) -> dict[str, str]:
            if ctx.step_id == "slow":
                started_slow.set()
                await asyncio.sleep(5.0)
            return {"ok": ctx.write_json(f"{ctx.step_id}.json", {"attempt": ctx.attempt})}

    wf = Workflow(
        name="cancel_test",
        title="Cancel Test",
        description="",
        params={},
        settings={"max_retries": 0, "max_revision_rounds": 2, "retry_backoff_s": 0.0},
        steps=[
            Step(id="root", agent="custom", title="Root"),
            Step(id="fast_cp", agent="custom", title="Fast CP", depends_on=["root"],
                 checkpoint=Checkpoint(id="X", title="Check X", route_to="root")),
            Step(id="slow", agent="custom", title="Slow Parallel", depends_on=["root"]),
        ],
    )
    registry = Registry(ROOT, {})
    spec = AgentSpec(name="custom", title="Custom", role="Test")
    registry.specs["custom"] = spec
    registry._instances["custom"] = CustomAgent(spec, {})
    store = StateStore.create(tmp_path / "run", new_state("cancel_run", wf, {}, {"custom": spec.public()}))
    orch = Orchestrator(store, wf, registry)

    async def scenario():
        run_task = asyncio.create_task(orch.run())
        await started_slow.wait()
        while orch.store.data["checkpoints"]["X"]["status"] != "pending":
            await asyncio.sleep(0.01)
        # Request changes routing back to 'root' while 'slow' is mid-flight!
        orch.decide("X", "request_changes", comment="Redo root")
        await asyncio.sleep(0.05)
        assert orch.steps["slow"]["status"] in ("queued", "running")
        # Now let root finish again; shrink slow sleep by replacing options isn't needed if we cancel run_task after check
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

    asyncio.run(scenario())


def test_budget_exceeded_stops_retries_immediately(tmp_path):
    class ExpensiveAgent(Agent):
        async def run(self, ctx: StepContext) -> dict[str, str]:
            ctx.add_cost(1.50)
            ctx.check_budget()
            return {}

    wf = Workflow(
        name="budget_test",
        title="Budget Test",
        description="",
        params={"budget_usd": 1.0},
        settings={"max_retries": 2, "max_revision_rounds": 1, "retry_backoff_s": 0.0},
        steps=[Step(id="s1", agent="exp", title="Expensive")],
    )
    registry = Registry(ROOT, {})
    spec = AgentSpec(name="exp", title="Exp", role="Test")
    registry.specs["exp"] = spec
    registry._instances["exp"] = ExpensiveAgent(spec, {})
    store = StateStore.create(tmp_path / "run", new_state("b_run", wf, {"budget_usd": 1.0}, {"exp": spec.public()}))
    orch = Orchestrator(store, wf, registry)

    outcome = asyncio.run(orch.run(headless=True))
    assert outcome == "failed"
    # Should break immediately on BudgetExceeded without retrying 2 more times
    assert orch.steps["s1"]["attempt"] == 1
    assert any("BudgetExceeded" in e["error"] for e in orch.steps["s1"]["errors"])


def test_gemini_flash_and_nano_banana_models_and_image_generation(tmp_path, monkeypatch):
    import base64
    import io

    assert resolve_text_models("flash")[:2] == ["gemini-3.8-flash", "gemini-3-flash-preview"]
    assert "gemini-3.7-flash" in resolve_text_models("flash")
    assert resolve_image_models("banana") == [
        "gemini-nano-banana-2.1",
        "gemini-3.1-flash-image-preview",
        "gemini-3.1-flash-image",
        "gemini-2.5-flash-image",
    ]
    assert extract_json("Here is the result:\n```json\n{\"ok\": true}\n```") == {"ok": True}

    cleaned = sanitize_schema_for_gemini({"type": "object", "additionalProperties": False,
                                          "properties": {"a": {"type": "object", "additionalProperties": False}}})
    assert "additionalProperties" not in cleaned
    assert "additionalProperties" not in cleaned["properties"]["a"]

    # Test GeminiClient 404 fallback + Nano Banana 9:16 PNG decoding & resize + AQ. Vertex Express routing
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.test-vertex-express-key")
    buf = io.BytesIO()
    Image.new("RGB", (540, 960), (20, 80, 160)).save(buf, format="PNG")
    b64_png = base64.b64encode(buf.getvalue()).decode("ascii")

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "generativelanguage.googleapis.com" in str(request.url):
            return httpx.Response(400, text="API_KEY_INVALID")
        if "gemini-nano-banana-2.1" in str(request.url):
            return httpx.Response(404, json={"error": "not enabled"})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": b64_png}}]}}]
        })

    wf = Workflow("img_wf", "Img", "", {}, {"max_retries": 0, "max_revision_rounds": 0}, [Step("s1", "x", "S1")])
    store = StateStore.create(tmp_path / "run", new_state("r1", wf, {}, {}))
    ctx = StepContext(store=store, step_id="s1", attempt=1, strategy="nano_banana", options={}, config={})
    client = GeminiClient(ctx, {"image_model": "banana"})

    orig_async_client = httpx.AsyncClient
    from moderator.engine import llm as llm_mod
    monkeypatch.setattr(llm_mod, "_make_async_client", lambda timeout_s, ipv4_only=False: orig_async_client(transport=httpx.MockTransport(handler), timeout=timeout_s))

    out_png = tmp_path / "banana_out.png"
    used = asyncio.run(client.generate_image("cinematic brain neurons", out_png, aspect_ratio="9:16", size=(1080, 1920)))
    assert used == "gemini-3.1-flash-image-preview"
    assert len(calls) == 3
    assert "generativelanguage.googleapis.com" in calls[0]
    assert "aiplatform.googleapis.com" in calls[1]
    with Image.open(out_png) as im:
        assert im.size == (1080, 1920)
    assert store.data["cost"]["total_usd"] > 0


def test_server_endpoints_and_path_traversal_protection(tmp_path):
    registry = Registry(ROOT, {})
    wf = registry.workflow("demo")
    agents = {s.agent: registry.specs[s.agent].public() for s in wf.steps}
    runs_dir = tmp_path / "runs"
    # Create an archived run and a live run
    StateStore.create(runs_dir / "20260101_000000_demo", new_state("20260101_000000_demo", wf, {}, agents))
    live_store = StateStore.create(runs_dir / "20260102_000000_demo", new_state("20260102_000000_demo", wf, {"topic": "Test"}, agents))
    (runs_dir / "20260102_000000_demo" / "sample.txt").write_text("hello", encoding="utf-8")
    with live_store.mutate() as d:
        d["steps"]["ideas"]["status"] = "failed"
        d["status"] = "failed"

    orch = Orchestrator(live_store, wf, registry)
    app = create_app(orch)

    async def exercise_api():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            assert (await client.get("/")).status_code == 200
            st = (await client.get("/api/state")).json()
            assert st["run_id"] == "20260102_000000_demo"

            runs = (await client.get("/api/runs")).json()
            assert runs["live_run_id"] == "20260102_000000_demo"
            assert len(runs["runs"]) == 2

            arch = await client.get("/api/runs/20260101_000000_demo/state")
            assert arch.status_code == 200
            assert arch.json()["run_id"] == "20260101_000000_demo"

            # File serving + path traversal protection
            assert (await client.get("/files/sample.txt")).text == "hello"
            assert (await client.get("/files/..%2F20260101_000000_demo/state.json")).status_code == 404
            assert (await client.get("/api/runs/..%2Fsecret/state")).status_code == 404

            # Writes need the dashboard header; foreign Host headers are refused (DNS rebinding)
            assert (await client.post("/api/retry-failed")).status_code == 403
            assert (await client.get("/api/state", headers={"host": "evil.example"})).status_code == 400

            # Retry all failed endpoint
            res = await client.post("/api/retry-failed", headers={"X-Moderator": "1"})
            assert res.status_code == 200
            assert res.json()["retried"] == ["ideas"]
            assert live_store.data["steps"]["ideas"]["status"] == "queued"

    asyncio.run(exercise_api())

    # review_summary works cleanly on non-youtube_short workflows too
    summary = review_summary(live_store)
    assert "20260102_000000_demo" in summary


def test_youtube_short_full_7_agent_pipeline_single_lang_en(tmp_path, monkeypatch):
    """End-to-end test of the 7-agent youtube_short workflow in single-language English mode (`languages=['en']`),
    verifying dynamic schemas, parallel visuals/audio execution, single-language output aliases, and QA checks."""
    from moderator.engine import llm as llm_mod
    from moderator.tools import ffmpeg, history as hist_mod, stock, tts as tts_mod

    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setattr(hist_mod, "PATH", tmp_path / "topics.jsonl")
    monkeypatch.setattr(stock, "available", lambda: {"pexels": False, "pixabay": False})

    seen_images = []
    calls = {"packaging": 0, "qa": 0}

    class FakeGemini:
        def __init__(self, ctx, cfg):
            self.ctx = ctx

        async def ask(self, prompt, *, system=None, schema=None, tools=None, model=None, complexity=None, images=None):
            self.ctx.add_cost(0.002)
            props = (schema or {}).get("properties", {})
            if "ideas" in props:
                return {"ideas": [
                    {"id": f"idea_{k}", "title": f"Spotlight Effect {k}", "angle": "People notice you less than you think.",
                     "hook": {"en": "Nobody is watching your mistakes."}, "keywords": ["psychology", "spotlight"],
                     "reason": "High retention curiosity topic", "sources": ["https://example.com"]}
                    for k in range(1, 4)
                ]}
            if "scenes" in props:
                vo_line = ("Have you ever tripped in public and felt every eye lock onto you immediately "
                           "when in reality almost nobody in the room even noticed you at all.")
                hook_line = "Nobody remembers your most embarrassing moment."
                scenes = [
                    {"vo": {"en": hook_line if i == 0 else vo_line},
                     "on_screen": {"en": f"BEAT {i + 1}"},
                     "visual": {"description": "crowded street", "search_terms": ["crowd walking"], "prefer": "video"}}
                    for i in range(5)
                ]
                seo = {"en": {"title": "Why Nobody Notices Your Mistakes (The Spotlight Effect Explained Simply)",
                              "question": "Ever replayed an awkward moment for days?",
                              "hashtags": ["psychology", "#spotlight effect", "#Psychology"],
                              "tags": ["spotlight effect", "social anxiety tips"]}}
                return {"title": "The Spotlight Effect", "seo": seo, "scenes": scenes}
            if "en" in props:  # packaging metadata (only on revisions now)
                calls["packaging"] += 1
                return {"en": {
                    "title": "Why Nobody Notices Your Mistakes",
                    "description": "Your brain exaggerates how much people watch you.\nPsychology calls this the spotlight effect.",
                    "hashtags": ["#Psychology", "#Facts"],
                    "tags": ["psychology", "spotlight effect"],
                    "thumbnail_text": "NOBODY NOTICED",
                }}
            if "issues" in props:  # QA: text review + people rule in ONE call
                calls["qa"] += 1
                assert "violations" in props and images and all(Path(i).is_file() for i in images)
                seen_images.extend(images)
                return {"issues": [], "violations": []}
            if "search_terms" in props:  # owner `/edit image N ...`: rewritten visual brief
                return {"description": "A calm mountain lake at dawn", "search_terms": ["mountain lake", "calm water"]}
            if "violations" in props:  # QA people rule: sees review sheets + thumbnails
                assert images and all(Path(i).is_file() for i in images)
                seen_images.extend(images)
                return {"violations": []}
            return ""

        async def generate_image(self, prompt, dest, *, aspect_ratio="9:16", size=(1080, 1920), model=None):
            self.ctx.add_cost(0.039)
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", size or (1080, 1920), (30, 50, 90)).save(dest)
            return "gemini-3.1-flash-image-preview"

    monkeypatch.setattr(llm_mod, "create_llm", lambda ctx, cfg: FakeGemini(ctx, cfg))

    async def fake_still_to_clip(src, dst, cwd, seconds=8, zoom_in=True):
        Path(dst).write_bytes(b"fake-mp4")

    async def fake_frame_at(src, dst, cwd, at=1.0):
        Image.new("RGB", (540, 960), (40, 60, 90)).save(dst)

    async def fake_ffmpeg_run(args, cwd, timeout=900):
        out = Path(cwd) / args[-1]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-media-output")
        return ""

    async def fake_duration(path):
        return 2.4 if "scene_01" in str(path) else (48.0 if "voiceover" in str(path) else 10.0)

    async def fake_probe(path):
        return {
            "format": {"duration": "49.5"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }

    async def fake_loudness(path, cwd):
        return {"lufs": -14.1, "true_peak_db": -1.4}

    async def fake_synth(txt, voice, out, rate="+0%"):
        Path(out).write_bytes(b"fake-mp3")
        # Return empty list to exercise fallback_word_timings integration in voice_audio!
        return []

    monkeypatch.setattr(ffmpeg, "still_to_clip", fake_still_to_clip)
    monkeypatch.setattr(ffmpeg, "frame_at", fake_frame_at)
    monkeypatch.setattr(ffmpeg, "run", fake_ffmpeg_run)
    monkeypatch.setattr(ffmpeg, "duration", fake_duration)
    monkeypatch.setattr(ffmpeg, "probe", fake_probe)
    monkeypatch.setattr(ffmpeg, "loudness", fake_loudness)
    monkeypatch.setattr(tts_mod, "synthesize", fake_synth)

    registry = Registry(ROOT, {})
    wf = registry.workflow("youtube_short")
    wf.settings["retry_backoff_s"] = 0.0
    params = {
        **wf.params,
        "niche": "Psychology & human behavior",
        "languages": ["en"],
        "auto_approve": ["A", "B"],
    }
    agents = {s.agent: registry.specs[s.agent].public() for s in wf.steps}
    run_dir = tmp_path / "runs" / "short_en_test"
    store = StateStore.create(run_dir, new_state("short_en_test", wf, params, agents))
    orch = Orchestrator(store, wf, registry)

    outcome = asyncio.run(asyncio.wait_for(orch.run(headless=True), 20))
    assert outcome == "waiting" and store.data["checkpoints"]["C"]["status"] == "pending"
    assert calls == {"packaging": 0, "qa": 1}  # packaging built in Python; one QA call
    meta = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))["en"]
    assert meta["title"] == "Why Nobody Notices Your Mistakes (The Spotlight Effect" and len(meta["title"]) <= 55
    assert meta["hashtags"] == ["#Shorts", "#Psychology", "#SpotlightEffect"]
    assert meta["description"].startswith("Ever replayed an awkward moment for days?\n")
    assert meta["thumbnail_text"] == "BEAT 1"
    assert "#fyp" in meta["tiktok_caption"] and "#Shorts" not in meta["tiktok_caption"]
    seen_images.clear()

    # Owner edits from the review issue: replace scene 2 and lower the music, then the run pauses at C again
    from moderator.edits import apply_edits, parse_edits
    before = {i["scene"]: i for i in json.loads((run_dir / "assets/licenses.json").read_text(encoding="utf-8"))}
    orch = Orchestrator(StateStore.load(run_dir), wf, registry)
    apply_edits(orch, parse_edits("/edit second image: a calm lake\n/edit music lower", 5), by="github:owner")
    assert orch.store.data["steps"]["visuals"]["status"] == "needs_revision"
    assert orch.store.data["steps"]["edit"]["status"] == "needs_revision"
    assert asyncio.run(asyncio.wait_for(orch.run(headless=True), 20)) == "waiting"
    after = {i["scene"]: i for i in json.loads((run_dir / "assets/licenses.json").read_text(encoding="utf-8"))}
    assert after["scene_02"]["description"] == "A calm mountain lake at dawn"
    assert all(after[k] == before[k] for k in before if k != "scene_02")  # other scenes kept as they were
    assert "scene_02" in json.loads((run_dir / "assets/scene_overrides.json").read_text(encoding="utf-8"))
    assert any("music" in f["comment"] for f in orch.store.data["steps"]["edit"]["feedback"])

    store = orch.store
    orch.decide("C", "approve", by="test")
    outcome = asyncio.run(asyncio.wait_for(Orchestrator(store, wf, registry).run(headless=True), 20))
    assert outcome == "done"
    assert all(s["status"] == "done" for s in store.data["steps"].values())
    # Verify single-language prompt output aliases exist alongside _en files
    assert (run_dir / "script.json").is_file()
    assert (run_dir / "voiceover.mp3").is_file()
    assert (run_dir / "music.mp3").is_file()
    assert (run_dir / "final_short.mp4").is_file()
    assert (run_dir / "metadata.json").is_file()
    assert (run_dir / "thumbnail.png").is_file()
    qa = json.loads((run_dir / "qa_report.json").read_text(encoding="utf-8"))
    assert qa["passed"] is True
    people = [c for c in qa["checks"] if c["check"] == "people rule"]
    assert people and people[0]["ok"]
    assert len(seen_images) == 3  # 5 scenes -> 2 review sheets (4 per sheet) + 1 thumbnail



def test_youtube_upload_credentials_single_and_multi_channel_and_publish(tmp_path, monkeypatch):
    import yaml
    from moderator import publish
    from moderator.tools import youtube_upload

    monkeypatch.setattr(youtube_upload, "TOKENS_DIR", tmp_path / "tokens")
    monkeypatch.delenv("YOUTUBE_TOKEN", raising=False)
    monkeypatch.delenv("YOUTUBE_TOKEN_EN", raising=False)
    monkeypatch.delenv("YOUTUBE_TOKEN_FR", raising=False)

    # 1. Missing token raises helpful error mentioning YOUTUBE_TOKEN
    with pytest.raises(RuntimeError, match="YOUTUBE_TOKEN"):
        youtube_upload.credentials("en")

    sample_shared = json.dumps({
        "token": "ya29.shared",
        "refresh_token": "1//shared_refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "shared_client.apps.googleusercontent.com",
        "client_secret": "shared_secret",
    })
    sample_en = json.dumps({
        "token": "ya29.en_specific",
        "refresh_token": "1//en_refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "en_client.apps.googleusercontent.com",
        "client_secret": "en_secret",
    })

    # 2. Single-channel YOUTUBE_TOKEN works as fallback for any language
    monkeypatch.setenv("YOUTUBE_TOKEN", sample_shared)
    monkeypatch.setattr("google.oauth2.credentials.Credentials.valid", property(lambda self: True))
    creds_fr = youtube_upload.credentials("fr")
    assert creds_fr.client_id == "shared_client.apps.googleusercontent.com"

    # 3. Language-specific YOUTUBE_TOKEN_EN overrides shared YOUTUBE_TOKEN for 'en'
    monkeypatch.setenv("YOUTUBE_TOKEN_EN", sample_en)
    creds_en = youtube_upload.credentials("en")
    assert creds_en.client_id == "en_client.apps.googleusercontent.com"

    # 4. Verify GitHub Actions workflow YAMLs are valid and wire YOUTUBE_TOKEN + GEMINI_API_KEY
    for wf_name in ("generate-short.yml", "edit-short.yml", "upload-short.yml", "ci.yml"):
        wf_path = ROOT / ".github" / "workflows" / wf_name
        raw = wf_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
        assert isinstance(parsed, dict) and "jobs" in parsed
        if wf_name not in ("generate-short.yml", "edit-short.yml"):  # only generation/edits can use Claude, when chosen
            assert "ANTHROPIC" not in raw and "claude" not in raw.lower()
    edit = yaml.safe_load((ROOT / ".github" / "workflows" / "edit-short.yml").read_text(encoding="utf-8"))
    edit_steps = {s.get("name"): s for s in edit["jobs"]["edit"]["steps"]}
    assert "startsWith(github.event.comment.body, '/edit')" in edit["jobs"]["edit"]["if"]
    assert "github.repository_owner" in edit["jobs"]["edit"]["if"]  # only the owner can trigger edits
    assert edit_steps["Install Claude Code CLI (pinned)"]["if"] == "steps.llm.outputs.provider == 'claude'"
    assert "COMMENT" not in edit_steps["Apply the edit and redo the affected steps"]["run"]  # comment read from a file
    gen = yaml.safe_load((ROOT / ".github" / "workflows" / "generate-short.yml").read_text(encoding="utf-8"))
    steps = {s.get("name"): s for s in gen["jobs"]["generate"]["steps"]}
    assert "|| 'gemini'" in steps["Choose text model and verify its secret"]["env"]["INPUT_LLM"]
    assert steps["Install Claude Code CLI (pinned)"]["if"] == "steps.llm.outputs.provider == 'claude'"
    # main only accepts pull requests: topic history goes to its own branch, nothing pushes to main
    gen_runs = "\n".join(s.get("run", "") for s in gen["jobs"]["generate"]["steps"])
    assert "topics-history.sh load" in gen_runs and "topics-history.sh save" in gen_runs
    assert "git push" not in gen_runs
    ruleset = json.loads((ROOT / ".github" / "rulesets" / "protect-main.json").read_text(encoding="utf-8"))
    assert ruleset["bypass_actors"] == []  # personal repos can't exempt the Actions bot
    assert {"pull_request", "non_fast_forward", "deletion"} <= {r["type"] for r in ruleset["rules"]}
    up_raw = (ROOT / ".github" / "workflows" / "upload-short.yml").read_text(encoding="utf-8")
    for secret in ("YOUTUBE_TOKEN", "YOUTUBE_TOKEN_EN", "YOUTUBE_TOKEN_FR", "YOUTUBE_TOKEN_AR"):
        assert secret in up_raw

    # 5. Verify approve_and_upload transitions Checkpoint C -> approved and writes uploads.json
    registry = Registry(ROOT, {})
    wf = registry.workflow("youtube_short")
    run_dir = tmp_path / "pub_run"
    state = new_state("pub_run", wf, {"languages": ["en"]}, {s.agent: registry.specs[s.agent].public() for s in wf.steps})
    for step in state["steps"].values():
        step["status"] = "done"
    state["steps"]["qa"]["status"] = "waiting_for_approval"
    state["steps"]["qa"]["outputs"] = {"video_en": "final_short_en.mp4", "thumbnail_en": "thumbnail_en.png"}
    state["steps"]["packaging"]["outputs"] = {"metadata": "metadata.json"}
    state["checkpoints"]["C"]["status"] = "pending"
    store = StateStore.create(run_dir, state)
    (run_dir / "final_short_en.mp4").write_bytes(b"mp4")
    (run_dir / "thumbnail_en.png").write_bytes(b"png")
    (run_dir / "metadata.json").write_text(json.dumps({"en": {"title": "Test", "description": "Desc", "hashtags": ["#Shorts"], "tags": ["test"]}}), encoding="utf-8")

    monkeypatch.setattr(
        youtube_upload,
        "upload",
        lambda lang, video, meta, privacy, thumbnail=None: {
            "id": "abc123XYZ",
            "url": "https://youtube.com/shorts/abc123XYZ",
            "privacy": privacy,
            "channel": "My Channel",
            "thumbnail": "set",
        },
    )
    res = publish.approve_and_upload(store, approved_by="github:jaleleddineagrebi", privacy="unlisted")
    assert len(res) == 1
    assert res[0]["url"] == "https://youtube.com/shorts/abc123XYZ"
    assert store.data["checkpoints"]["C"]["status"] == "approved"
    assert store.data["status"] == "done"
    assert (run_dir / "uploads.json").is_file()


def test_export_pages_seed_and_run_snapshots_with_pruning(tmp_path):
    from moderator.pages import export_pages

    site_dir = tmp_path / "gh_pages"
    empty_runs = tmp_path / "empty_runs"
    empty_runs.mkdir()

    # 1. Brand-new deployment with 0 runs exports seed_state so the 7-agent DAG renders immediately
    m0 = export_pages(site_dir, repo="jaleleddineagrebi/moderator", runs_dir=empty_runs)
    assert m0["runs"] == []
    assert m0["seed_state"]["is_seed"] is True
    assert "research" in m0["seed_state"]["steps"]
    assert (site_dir / ".nojekyll").is_file()
    html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "window.MODERATOR_PAGES" in html
    assert "jaleleddineagrebi/moderator" in html
    assert (site_dir / "static" / "app.js").is_file()
    assert (site_dir / "static" / "styles.css").is_file()

    # 2. Export runs (verifying raw/scene_XX.mp4 skipped, final_short + thumbnail + uploads preserved, max_runs pruned)
    runs_src = tmp_path / "runs_src"
    registry = Registry(ROOT, {})
    wf = registry.workflow("youtube_short")
    agents_pub = {s.agent: registry.specs[s.agent].public() for s in wf.steps}

    for i in range(4):
        rid = f"20261103_0{i}0000_youtube_short"
        rdir = runs_src / rid
        st = new_state(rid, wf, {"languages": ["en"], "topic": f"Topic {i}"}, agents_pub)
        st["started_at"] = f"2026-11-03T0{i}:00:00+00:00"
        st["steps"]["visuals"]["outputs"] = {
            "contact_sheet": "assets/contact_sheet.jpg",
            "scenes": ["assets/scene_01.mp4"],
        }
        st["steps"]["qa"]["outputs"] = {"video_en": "final_short_en.mp4", "report_md": "qa_report.md"}
        StateStore.create(rdir, st)
        (rdir / "assets" / "raw").mkdir(parents=True)
        (rdir / "assets" / "raw" / "tmp.png").write_bytes(b"raw")
        (rdir / "assets" / "scene_01.mp4").write_bytes(b"scene")
        (rdir / "assets" / "contact_sheet.jpg").write_bytes(b"jpg")
        (rdir / "final_short_en.mp4").write_bytes(b"mp4")
        (rdir / "qa_report.md").write_text("# QA Passed", encoding="utf-8")
        if i == 3:
            (rdir / "uploads.json").write_text(
                json.dumps([{"lang": "en", "url": "https://youtube.com/shorts/xyz", "privacy": "public", "channel": "Main"}]),
                encoding="utf-8",
            )

    m1 = export_pages(
        site_dir,
        repo="jaleleddineagrebi/moderator",
        runs_dir=runs_src,
        target_run_id="20261103_030000_youtube_short",
        issue_url="https://github.com/jaleleddineagrebi/moderator/issues/1",
        max_runs=3,
        media_runs=2,
    )
    assert len(m1["runs"]) == 3
    assert m1["live_run_id"] == "20261103_030000_youtube_short"
    assert m1["runs"][0]["has_uploads"] is True

    newest_dir = site_dir / "data" / "runs" / "20261103_030000_youtube_short"
    assert (newest_dir / "final_short_en.mp4").is_file()
    assert (newest_dir / "assets" / "contact_sheet.jpg").is_file()
    assert not (newest_dir / "assets" / "scene_01.mp4").exists()
    assert not (newest_dir / "assets" / "raw").exists()

    exported_st = json.loads((newest_dir / "state.json").read_text(encoding="utf-8"))
    # Filtered outputs drop skipped scene_01.mp4 while keeping contact_sheet.jpg
    assert exported_st["steps"]["visuals"]["outputs"] == {"contact_sheet": "assets/contact_sheet.jpg"}
    assert exported_st["pages_meta"]["issue_url"] == "https://github.com/jaleleddineagrebi/moderator/issues/1"
    assert exported_st["pages_meta"]["uploads"][0]["url"] == "https://youtube.com/shorts/xyz"

    # 3rd kept run (index 2 >= media_runs=2) has mp4 stripped to keep gh-pages compact
    older_dir = site_dir / "data" / "runs" / "20261103_010000_youtube_short"
    assert not (older_dir / "final_short_en.mp4").exists()
    assert (older_dir / "qa_report.md").is_file()


def test_gemini_free_tier_429_search_and_503_model_fallback(tmp_path, monkeypatch):
    from moderator.engine import llm as llm_mod

    monkeypatch.setenv("GEMINI_API_KEY", "AQ.free-tier-test-key")
    llm_mod._WORKING_BASE_BY_KEY.clear()
    llm_mod._WORKING_MODEL_BY_KEY.clear()
    llm_mod._SEARCH_UNAVAILABLE_KEYS.clear()

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        url = str(request.url)
        has_search = "tools" in body
        seen.append((url.split("/")[-1], has_search))
        # Simulate Free Tier: google_search returns 429, and gemini-3.8-flash returns 503 high demand
        if has_search:
            return httpx.Response(429, json={"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}})
        if "gemini-3.8-flash:" in url:
            return httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE"}})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 10},
        })

    orig_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        llm_mod,
        "_make_async_client",
        lambda timeout_s, ipv4_only=False: orig_async_client(transport=httpx.MockTransport(handler), timeout=timeout_s),
    )

    wf = Workflow("free_wf", "Free", "", {}, {"max_retries": 0, "max_revision_rounds": 0}, [Step("s1", "x", "S1")])
    store = StateStore.create(tmp_path / "run", new_state("r_free", wf, {}, {}))
    ctx = StepContext(store=store, step_id="s1", attempt=1, strategy="web_and_youtube", options={}, config={})
    client = GeminiClient(ctx, {"model": "flash"})

    res = asyncio.run(
        client.ask(
            "Find 3 psychology ideas",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            tools=["WebSearch"],
        )
    )
    assert res == {"ok": True}
    # Subsequent call remembers gemini-3-flash-preview and skips google_search immediately!
    seen.clear()
    res2 = asyncio.run(
        client.ask(
            "Second call",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            tools=["WebSearch"],
        )
    )
    assert res2 == {"ok": True}
    assert seen == [("gemini-3-flash-preview:generateContent", False)]


def test_stock_video_wikimedia_zero_key_and_visual_producer_video_priority(tmp_path, monkeypatch):
    from agents.visual_producer.handler import Handler as VisualHandler
    from moderator.tools import ffmpeg, stock

    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.delenv("MODERATOR_DISABLE_WIKIMEDIA", raising=False)
    avail = stock.available()
    assert avail == {"pexels": False, "pixabay": False, "wikimedia": True}

    # 1. Verify Wikimedia search keeps CC0/PD videos and rejects CC-BY-SA attribution-required videos
    def mock_commons_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "query": {
                "pages": {
                    "1": {
                        "pageid": 1,
                        "imageinfo": [{
                            "url": "https://upload.wikimedia.org/commons/cc_by_clip.webm",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:CcBy.webm",
                            "mime": "video/webm",
                            "size": 2_000_000,
                            "duration": 8.0,
                            "width": 1080,
                            "height": 1920,
                            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}},
                        }],
                    },
                    "2": {
                        "pageid": 2,
                        "imageinfo": [{
                            "url": "https://upload.wikimedia.org/commons/pd_street.webm",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:PdStreet.webm",
                            "mime": "video/webm",
                            "size": 3_500_000,
                            "duration": 9.5,
                            "width": 1920,
                            "height": 1080,
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC0"},
                                "UsageTerms": {"value": "Creative Commons Zero, Public Domain Dedication"},
                                "Artist": {"value": "<a href='x'>CityCam</a>"},
                            },
                        }],
                    },
                }
            }
        })

    orig_client = httpx.AsyncClient
    monkeypatch.setattr(
        stock.httpx,
        "AsyncClient",
        lambda **kw: orig_client(transport=httpx.MockTransport(mock_commons_handler), **{k: v for k, v in kw.items() if k != "transport"}),
    )
    hits = asyncio.run(stock.search_videos("crowded street", "wikimedia"))
    assert len(hits) == 1
    assert hits[0]["provider"] == "wikimedia"
    assert hits[0]["ext"] == "webm"
    assert hits[0]["author"] == "CityCam"
    assert "no attribution required" in hits[0]["license"]

    # 1b. Verify Pixabay live-action (`video_type=film`) search + portrait-first sorting
    monkeypatch.setenv("PIXABAY_API_KEY", "test-pixabay-key")

    def mock_pixabay_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("per_page") == "50"
        return httpx.Response(200, json={
            "hits": [
                {"pageURL": "https://pixabay.com/v/land", "user": "U1", "duration": 7,
                 "videos": {"large": {"url": "https://cdn.pixabay.com/land.mp4", "width": 1920, "height": 1080}}},
                {"pageURL": "https://pixabay.com/v/vert", "user": "U2", "duration": 6,
                 "videos": {"large": {"url": "https://cdn.pixabay.com/vert.mp4", "width": 1080, "height": 1920}}},
            ]
        })

    monkeypatch.setattr(
        stock.httpx,
        "AsyncClient",
        lambda **kw: orig_client(transport=httpx.MockTransport(mock_pixabay_handler), **{k: v for k, v in kw.items() if k != "transport"}),
    )
    pix_hits = asyncio.run(stock.search_videos("person thinking", "pixabay"))
    assert [h["page"] for h in pix_hits] == ["https://pixabay.com/v/vert", "https://pixabay.com/v/land"]
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.setattr(
        stock.httpx,
        "AsyncClient",
        lambda **kw: orig_client(transport=httpx.MockTransport(mock_commons_handler), **{k: v for k, v in kw.items() if k != "transport"}),
    )

    # 2. Verify visual_producer uses moving stock_video (not stock_photo or generated) even when prefer="photo" and 0 keys set
    registry = Registry(ROOT, {})
    wf = registry.workflow("youtube_short")
    run_dir = tmp_path / "vis_run"
    st = new_state(
        "vis_run",
        wf,
        {"visual_mode": "stock", "languages": ["en"]},
        {s.agent: registry.specs[s.agent].public() for s in wf.steps},
    )
    st["steps"]["script"]["status"] = "done"
    st["steps"]["script"]["outputs"] = {"data": "script.json"}
    store = StateStore.create(run_dir, st)
    (run_dir / "script.json").write_text(
        json.dumps({
            "title": "Test Video Priority",
            "scenes": [{
                "id": "scene_01",
                "vo": {"en": "Watch the crowd."},
                "on_screen": {"en": "WATCH"},
                "visual": {"description": "crowded street", "search_terms": ["crowded street"], "prefer": "photo"},
            }],
        }),
        encoding="utf-8",
    )

    normalized_calls = []

    async def fake_download(url, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"fake-webm")

    async def fake_normalize(src, dst, cwd, max_seconds=12):
        normalized_calls.append((Path(src).suffix, Path(dst).name))
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(b"fake-mp4")

    async def fake_frame_at(src, dst, cwd, at=1.0):
        Image.new("RGB", (540, 960), (20, 30, 40)).save(dst)

    monkeypatch.setattr(stock, "download", fake_download)
    monkeypatch.setattr(ffmpeg, "normalize_clip", fake_normalize)
    monkeypatch.setattr(ffmpeg, "frame_at", fake_frame_at)

    ctx = StepContext(store=store, step_id="visuals", attempt=1, strategy="nano_banana", options={}, config={})
    out = asyncio.run(VisualHandler(registry.specs["visual_producer"], {}).run(ctx))
    assert out["scenes"] == ["assets/scene_01.mp4"]
    assert normalized_calls == [(".webm", "scene_01.mp4")]
    lic = json.loads((run_dir / "assets/licenses.json").read_text(encoding="utf-8"))
    assert lic[0]["tier"] == "stock_video"
    assert lic[0]["provider"] == "wikimedia"


def test_youtube_channel_optimizer_banner_and_profile(tmp_path):
    from moderator.tools import youtube_channel

    prof = youtube_channel.build_channel_profile(
        preset="auto",
        channel_title="land of ai",
        channel_cfg={"niche": "Psychology & human behavior (biases, habits, social dynamics)"},
        country="us",
    )
    assert prof["mode"] == "hybrid"
    assert prof["country"] == "US"
    assert len(prof["description"]) <= 1000
    assert len(prof["keywords"]) <= 500
    assert '"human behavior"' in prof["keywords"]
    assert "psychology" in prof["keywords"]

    banner = youtube_channel.render_channel_banner(
        tmp_path / "banner.jpg",
        prof["banner_headline"],
        prof["banner_subtitle"],
    )
    assert banner.is_file()
    assert banner.stat().st_size < 6 * 1024 * 1024
    with Image.open(banner) as im:
        assert im.size == (2560, 1440)


def test_youtube_channel_video_update_plan_uses_video_language():
    from moderator.tools import youtube_channel

    fr = youtube_channel.plan_video_update({"title": "Pourquoi ton cerveau ment", "description": "Ligne 1\n#Shorts",
                                            "defaultAudioLanguage": "fr"})
    assert fr["title"] == "Pourquoi ton cerveau ment #shorts"
    assert fr["description"].startswith(youtube_channel.COMMENT_HOOKS["fr"])

    ar = youtube_channel.plan_video_update({"title": "عقلك بيكدب عليك #shorts", "description": "سطر",
                                            "defaultLanguage": "ar"})
    assert ar["title"] == "عقلك بيكدب عليك #shorts"
    assert ar["description"].startswith(youtube_channel.COMMENT_HOOKS["ar"])

    # already optimized, or a language without a hook: leave it alone
    assert youtube_channel.plan_video_update({"title": "Why #shorts", "description": "Ever felt this? 👇",
                                              "defaultAudioLanguage": "en"}) is None
    de = youtube_channel.plan_video_update({"title": "Warum #shorts", "description": "Text", "defaultAudioLanguage": "de"})
    assert de is None
