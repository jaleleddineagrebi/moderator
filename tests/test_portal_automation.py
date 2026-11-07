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
