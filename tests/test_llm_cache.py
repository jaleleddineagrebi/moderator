import json
import time
from pathlib import Path
import pytest
from moderator.engine.llm_cache import LLMCache


def test_cache_key_deterministic(tmp_path: Path):
    cache = LLMCache(db_path=tmp_path / "test.sqlite")
    k1 = cache.compute_key(
        provider="gemini",
        model="gemini-3.8-flash",
        prompt="Explain confirmation bias in 2 sentences.",
        system="You are a psychology expert.",
        schema={"type": "object", "properties": {"title": {"type": "string"}}},
    )
    k2 = cache.compute_key(
        provider="gemini",
        model="gemini-3.8-flash",
        prompt="Explain confirmation bias in 2 sentences.",
        system="You are a psychology expert.",
        schema={"type": "object", "properties": {"title": {"type": "string"}}},
    )
    assert k1 == k2
    assert len(k1) == 64


def test_cache_set_and_get(tmp_path: Path):
    cache = LLMCache(db_path=tmp_path / "test.sqlite", default_ttl_s=3600)
    key = cache.compute_key(provider="gemini", model="gemini-3.8-flash", prompt="Hello")
    
    # Initially miss
    assert cache.get(key) is None

    # Store string
    cache.set(key, provider="gemini", model="gemini-3.8-flash", response="Hello world", tokens_in=5, tokens_out=10, cost_usd=0.0001)
    
    # Hit
    val = cache.get(key)
    assert val == "Hello world"

    stats = cache.get_stats()
    assert stats["total_entries"] == 1
    assert stats["total_hits"] == 1
    assert stats["tokens_saved"] == 15
    assert stats["usd_saved"] == 0.0001


def test_cache_json_response(tmp_path: Path):
    cache = LLMCache(db_path=tmp_path / "test.sqlite")
    key = cache.compute_key(provider="claude", model="sonnet", prompt="Return json", json_output=True)
    payload = {"status": "ok", "tags": ["psychology", "ai"]}
    
    cache.set(key, provider="claude", model="sonnet", response=payload, tokens_in=10, tokens_out=20, cost_usd=0.0002)
    cached = cache.get(key)
    assert cached == payload
    assert isinstance(cached, dict)


def test_cache_ttl_expiration(tmp_path: Path):
    # 1 second TTL
    cache = LLMCache(db_path=tmp_path / "test.sqlite", default_ttl_s=1)
    key = cache.compute_key(provider="gemini", model="flash", prompt="Short lived")
    cache.set(key, provider="gemini", model="flash", response="Soon expired", ttl_s=1)
    
    assert cache.get(key) == "Soon expired"
    time.sleep(1.1)
    assert cache.get(key) is None


def test_cache_clear(tmp_path: Path):
    cache = LLMCache(db_path=tmp_path / "test.sqlite")
    k1 = cache.compute_key(provider="gemini", model="flash", prompt="P1")
    k2 = cache.compute_key(provider="gemini", model="flash", prompt="P2")
    cache.set(k1, provider="gemini", model="flash", response="R1")
    cache.set(k2, provider="gemini", model="flash", response="R2")
    
    assert cache.get_stats()["total_entries"] == 2
    deleted = cache.clear()
    assert deleted == 2
    assert cache.get_stats()["total_entries"] == 0

