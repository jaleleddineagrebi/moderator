"""Gemini model routing by task complexity, thinking settings, token accounting and quota handling."""

import asyncio
import json

import httpx
import pytest

from moderator.engine import llm as llm_mod
from moderator.engine.agent import StepContext
from moderator.engine.llm import GeminiClient, classify_429, escalate, thinking_config
from moderator.engine.state import StateStore, new_state
from moderator.engine.workflow import Step, Workflow

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
OK = {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}],
      "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 100, "thoughtsTokenCount": 4000}}


def make_ctx(tmp_path, complexity="medium", attempt=1):
    wf = Workflow("w", "W", "", {}, {"max_retries": 0, "max_revision_rounds": 0}, [Step("s1", "x", "S1")])
    store = StateStore.create(tmp_path / "run", new_state("r", wf, {}, {}))
    return StepContext(store=store, step_id="s1", attempt=attempt, strategy="default", options={}, config={},
                       complexity=complexity)


@pytest.fixture
def gemini(monkeypatch):
    """Mock Gemini endpoint: `handler(model_id, body) -> httpx.Response`; records (model, body) per request."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-routing-test")
    monkeypatch.setenv("GEMINI_API_BASE", "https://gemini.test/v1beta/models")
    monkeypatch.setenv("MODERATOR_LLM_CACHE", "0")
    monkeypatch.setattr(llm_mod, "TRANSIENT_RETRY_DELAY_S", 0)
    for cache in (llm_mod._WORKING_BASE_BY_KEY, llm_mod._WORKING_MODEL_BY_KEY, llm_mod._SEARCH_UNAVAILABLE_KEYS,
                  llm_mod._EXHAUSTED_MODELS):
        cache.clear()
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(llm_mod.asyncio, "sleep", fake_sleep)
    state = {"handler": lambda model, body: httpx.Response(200, json=OK), "calls": [], "sleeps": sleeps}

    def transport(request: httpx.Request) -> httpx.Response:
        model = str(request.url).rsplit("/", 1)[-1].split(":")[0]
        body = json.loads(request.content)
        state["calls"].append((model, body))
        return state["handler"](model, body)

    orig = httpx.AsyncClient
    monkeypatch.setattr(llm_mod, "_make_async_client",
                        lambda timeout_s, ipv4_only=False: orig(transport=httpx.MockTransport(transport), timeout=timeout_s))
    return state


def test_escalate_and_thinking_config():
    assert escalate("low", 0) == "low"
    assert escalate("low", 1) == "medium"
    assert escalate("medium", 5) == "high"
    assert escalate("bogus", 0) == "medium"
    assert thinking_config("gemini-3-flash-preview", "minimal") == {"thinkingLevel": "minimal"}
    assert thinking_config("gemini-3.1-pro-preview", "medium") == {"thinkingLevel": "high"}
    assert thinking_config("gemini-2.5-flash", "minimal") == {"thinkingBudget": 0}
    assert thinking_config("gemini-2.5-pro", "minimal") == {"thinkingBudget": 128}
    assert thinking_config("gemini-3.1-flash-image", "high") is None


def test_complexity_picks_model_and_thinking(tmp_path, gemini):
    low = GeminiClient(make_ctx(tmp_path / "a", "low"), {})
    assert asyncio.run(low.ask("x", schema=SCHEMA)) == {"ok": True}
    model, body = gemini["calls"][-1]
    assert model == llm_mod.TEXT_MODEL_CHAINS["flash-lite"][0]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}

    high = GeminiClient(make_ctx(tmp_path / "b", "high"), {})
    asyncio.run(high.ask("x", schema=SCHEMA))
    model, body = gemini["calls"][-1]
    assert model == llm_mod.TEXT_MODEL_CHAINS["flash"][0]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"}

    # a per-call override and config tiers both apply
    custom = GeminiClient(make_ctx(tmp_path / "c", "high"), {"tiers": {"low": {"model": "pro", "thinking": "low"}}})
    asyncio.run(custom.ask("x", schema=SCHEMA, complexity="low"))
    model, body = gemini["calls"][-1]
    assert model == llm_mod.TEXT_MODEL_CHAINS["pro"][0]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


def test_retry_attempt_escalates_tier(tmp_path, gemini):
    client = GeminiClient(make_ctx(tmp_path, "low", attempt=2), {})
    assert client.route() == ("medium", "flash", "low")
    asyncio.run(client.ask("x", schema=SCHEMA))
    assert gemini["calls"][-1][0] == llm_mod.TEXT_MODEL_CHAINS["flash"][0]


def test_thinking_tokens_are_charged(tmp_path, gemini):
    ctx = make_ctx(tmp_path, "medium")
    asyncio.run(GeminiClient(ctx, {}).ask("x", schema=SCHEMA))
    model = gemini["calls"][-1][0]
    expected = llm_mod._estimate_token_cost(model, 1000, 100 + 4000)
    assert ctx.store.data["cost"]["total_usd"] == pytest.approx(expected, rel=1e-3)


def test_daily_quota_429_skips_model_for_rest_of_run(tmp_path, gemini):
    flash = llm_mod.TEXT_MODEL_CHAINS["flash"]
    daily = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
    gemini["handler"] = lambda m, b: httpx.Response(429, json=daily) if m == flash[0] else httpx.Response(200, json=OK)
    client = GeminiClient(make_ctx(tmp_path, "medium"), {})
    asyncio.run(client.ask("x", schema=SCHEMA))
    assert [m for m, _ in gemini["calls"]] == [flash[0], flash[1]]
    gemini["calls"].clear()
    asyncio.run(client.ask("y", schema=SCHEMA))
    assert [m for m, _ in gemini["calls"]] == [flash[1]]  # exhausted model is not called again
    assert gemini["sleeps"] == []


def test_per_minute_429_waits_and_retries_same_model(tmp_path, gemini):
    flash = llm_mod.TEXT_MODEL_CHAINS["flash"]
    per_minute = {"error": {"code": 429, "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerMinute"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "12s"}]}}
    responses = iter([httpx.Response(429, json=per_minute), httpx.Response(200, json=OK)])
    gemini["handler"] = lambda m, b: next(responses)
    asyncio.run(GeminiClient(make_ctx(tmp_path, "medium"), {}).ask("x", schema=SCHEMA))
    assert [m for m, _ in gemini["calls"]] == [flash[0], flash[0]]
    assert gemini["sleeps"] == [12.0]
    assert classify_429(httpx.Response(429, json=per_minute)) == (False, 12.0)


def test_model_rejecting_thinking_setting_is_retried_without_it(tmp_path, gemini):
    def handler(model, body):
        if "thinkingConfig" in body.get("generationConfig", {}):
            return httpx.Response(400, text='{"error": "Unknown name \\"thinkingLevel\\" at generation_config.thinking_config"}')
        return httpx.Response(200, json=OK)

    gemini["handler"] = handler
    assert asyncio.run(GeminiClient(make_ctx(tmp_path, "high"), {}).ask("x", schema=SCHEMA)) == {"ok": True}
    assert len(gemini["calls"]) == 2


def test_state_and_pages_never_store_api_keys(tmp_path, monkeypatch):
    from moderator.engine.state import redact

    monkeypatch.setenv("PIXABAY_API_KEY", "pixabay-secret-123456")
    msg = "Client error '429' for url 'https://pixabay.com/api/videos/?key=pixabay-secret-123456&q=brain'"
    assert "pixabay-secret" not in redact(msg)
    assert "key=***&q=brain" in redact(msg)
    assert redact("youtube ?part=x&key=AIzaOther&y=1") == "youtube ?part=x&key=***&y=1"

    ctx = make_ctx(tmp_path)
    ctx.store.log("s1", msg, "error")
    assert "pixabay-secret" not in (ctx.store.run_dir / "state.json").read_text(encoding="utf-8")
