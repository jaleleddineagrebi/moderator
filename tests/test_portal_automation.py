"""Tests for Psychology and AI Portal automation and native logic."""

from portal.automation.llm_router import NativeOptimizer


def test_native_slugify():
    raw = "Why Your Brain Overestimates AI: The Automation Bias (2026)!"
    assert NativeOptimizer.slugify(raw) == "why-your-brain-overestimates-ai-the-automation-bias-2026"


def test_clean_html_and_boilerplate():
    html = "<p>Recent research from <b>MIT</b> shows human-AI teaming. Check <a href='https://mit.edu'>link</a>.</p>"
    clean = NativeOptimizer.clean_html_and_boilerplate(html)
    assert "<p>" not in clean
    assert "https://mit.edu" not in clean
    assert "Recent research from MIT shows human-AI teaming. Check link ." in clean


def test_heuristic_keywords():
    title = "The Cognitive Bias of Generative AI Teaming"
    body = "In this experiment, participants exhibited cognitive automation bias when interacting with neural models."
    keywords = NativeOptimizer.extract_keywords_heuristics(title, body, top_n=3)
    assert "cognitive" in keywords or "bias" in keywords


def test_safe_json_extract():
    wrapped = "Here is the response:\n```json\n{\"title\": \"AI Psychology\", \"score\": 42}\n```\nHope it helps!"
    res = NativeOptimizer.safe_json_extract(wrapped)
    assert res["title"] == "AI Psychology"
    assert res["score"] == 42


import asyncio
from portal.automation.storage_service import StorageService


def test_storage_fallback_without_credentials():
    svc = StorageService()
    url = "https://images.unsplash.com/photo-123?w=800"
    persisted = asyncio.run(svc.persist_image_from_url(url, "test-slug"))
    assert persisted == url


import json

import httpx
import pytest

from moderator.engine.llm_cache import LLMCache
from portal.automation import llm_router
from portal.automation.llm_router import CostOptimizedLLMRouter, GEMINI_CHEAPEST

GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": '{"title": "T"}'}]}}],
             "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 500}}


@pytest.fixture
def router(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MODERATOR_LLM_CACHE", "1")  # tests/conftest.py turns the cache off globally
    cache = LLMCache(db_path=tmp_path / "cache.db")
    monkeypatch.setattr("moderator.engine.llm_cache.default_cache", cache)
    return CostOptimizedLLMRouter(), cache


def _mock_gemini(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(llm_router.httpx, "AsyncClient",
                        lambda *a, **kw: real(transport=httpx.MockTransport(handler), timeout=kw.get("timeout")))


@pytest.mark.parametrize("complexity", ["trivial", "low", "high"])
def test_router_always_uses_cheapest_gemini_model_and_caches(router, monkeypatch, complexity):
    r, cache = router
    models = []

    def handler(request):
        models.append(request.url.path.split("/models/")[1].split(":")[0])
        return httpx.Response(200, json=GEMINI_OK)

    _mock_gemini(monkeypatch, handler)
    res = asyncio.run(r.route_and_generate("write", complexity=complexity, json_output=True))
    assert models == [GEMINI_CHEAPEST[0]] and res.model_used == GEMINI_CHEAPEST[0]
    assert res.estimated_cost_usd == round((1000 * 0.25 + 500 * 1.50) / 1_000_000, 6)
    # second identical request is a cache hit: no HTTP call, no crash (regression: wrong LLMResponse fields)
    again = asyncio.run(r.route_and_generate("write", complexity=complexity, json_output=True))
    assert models == [GEMINI_CHEAPEST[0]] and again.model_used == "cache" and again.estimated_cost_usd == 0.0
    assert json.loads(again.content) == {"title": "T"}


def test_router_fallbacks_stay_on_lite_models_and_survive_timeouts_and_429(router, monkeypatch):
    r, _ = router
    seen = []

    def handler(request):
        model = request.url.path.split("/models/")[1].split(":")[0]
        seen.append(model)
        if model == GEMINI_CHEAPEST[0]:
            raise httpx.ReadTimeout("")  # the empty-message timeout from the failed GitHub run
        if model == GEMINI_CHEAPEST[1]:
            return httpx.Response(429, text="quota")
        return httpx.Response(200, json=GEMINI_OK)

    _mock_gemini(monkeypatch, handler)
    res = asyncio.run(r.route_and_generate("write", complexity="high", json_output=True, cache=False))
    assert seen == GEMINI_CHEAPEST[:3] and res.model_used == GEMINI_CHEAPEST[2]
    assert all("lite" in m for m in seen)  # never a pricier Flash/Pro


def test_cache_failure_never_breaks_generation(router, monkeypatch):
    r, cache = router
    _mock_gemini(monkeypatch, lambda request: httpx.Response(200, json=GEMINI_OK))

    def boom(*a, **kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(cache, "set", boom)
    monkeypatch.setattr(cache, "get", boom)
    assert asyncio.run(r.route_and_generate("write", json_output=True)).content == '{"title": "T"}'


def test_unparseable_json_is_not_cached(router, monkeypatch):
    r, cache = router
    bad = {"candidates": [{"content": {"parts": [{"text": "not json at all"}]}}]}
    _mock_gemini(monkeypatch, lambda request: httpx.Response(200, json=bad))
    asyncio.run(r.route_and_generate("write", json_output=True))
    key = cache.compute_key(provider="router", model="cheapest", prompt="write", system="", json_output=True)
    assert cache.get(key) is None
