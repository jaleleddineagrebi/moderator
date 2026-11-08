"""Persistent, deterministic SQLite-backed LLM response cache.

Saves token consumption, latency, and costs across Gemini, Claude, and portal pipelines.
Caches: (provider, model, prompt, system, schema, tools, images, json_output) -> response.
Can be bypassed per-call with `cache=False` or globally with `MODERATOR_LLM_CACHE=0`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, NamedTuple


class CacheEntry(NamedTuple):
    content: Any
    is_json: bool
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str
    created_at: float
    hit_count: int


class LLMCache:
    def __init__(self, db_path: Path | str | None = None, default_ttl_s: int = 7 * 86400, enabled: bool = True):
        self._force_enabled = False
        if db_path is None:
            cache_dir = Path(os.getenv("MODERATOR_CACHE_DIR", "history"))
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = cache_dir / "llm_cache.sqlite"
        else:
            self._force_enabled = True
        self.db_path = Path(db_path)
        self.default_ttl_s = int(os.getenv("MODERATOR_LLM_CACHE_TTL", str(default_ttl_s)))
        self._enabled = enabled
        self._force_enabled = False
        self._init_db()

    @property
    def is_enabled(self) -> bool:
        if self._force_enabled:
            return True
        if not self._enabled:
            return False
        return os.getenv("MODERATOR_LLM_CACHE", "1").lower() not in ("0", "false", "no", "off")

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS llm_cache (
                        cache_key TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        response_text TEXT NOT NULL,
                        is_json INTEGER NOT NULL DEFAULT 0,
                        tokens_in INTEGER NOT NULL DEFAULT 0,
                        tokens_out INTEGER NOT NULL DEFAULT 0,
                        cost_usd REAL NOT NULL DEFAULT 0.0,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        hit_count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON llm_cache (expires_at)")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cache_metrics (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        total_hits INTEGER NOT NULL DEFAULT 0,
                        tokens_saved INTEGER NOT NULL DEFAULT 0,
                        usd_saved REAL NOT NULL DEFAULT 0.0
                    )
                """)
                conn.execute("INSERT OR IGNORE INTO cache_metrics (id, total_hits, tokens_saved, usd_saved) VALUES (1, 0, 0, 0.0)")
        except Exception:
            pass  # Fails open if permission or disk issue

    @staticmethod
    def compute_key(
        provider: str,
        model: str,
        prompt: str,
        system: str | None = None,
        schema: Any | None = None,
        tools: list[str] | None = None,
        images: list[Path | str] | None = None,
        json_output: bool = False,
    ) -> str:
        """Create a deterministic SHA-256 fingerprint of the LLM request."""
        hasher = hashlib.sha256()
        hasher.update(provider.lower().strip().encode("utf-8"))
        hasher.update(b"||")
        hasher.update(model.lower().strip().encode("utf-8"))
        hasher.update(b"||")
        hasher.update(prompt.strip().encode("utf-8"))
        hasher.update(b"||")
        if system:
            hasher.update(system.strip().encode("utf-8"))
        hasher.update(b"||")
        if schema:
            hasher.update(json.dumps(schema, sort_keys=True).encode("utf-8"))
        hasher.update(b"||")
        if tools:
            hasher.update(",".join(sorted(tools)).encode("utf-8"))
        hasher.update(b"||")
        if json_output:
            hasher.update(b"json_output=true")
        hasher.update(b"||")
        for img in images or []:
            try:
                p = Path(img)
                if p.exists():
                    hasher.update(hashlib.md5(p.read_bytes()).hexdigest().encode("ascii"))
            except Exception:
                hasher.update(str(img).encode("utf-8"))
        return hasher.hexdigest()

    def get(self, cache_key: str) -> Any | None:
        """Lookup response by cache key. Returns parsed JSON or str, or None if miss/expired."""
        if not self.is_enabled:
            return None
        now = time.time()
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT response_text, is_json, tokens_in, tokens_out, cost_usd, model, hit_count, expires_at FROM llm_cache WHERE cache_key = ?",
                    (cache_key,)
                ).fetchone()
                if not row:
                    return None
                resp_text, is_json, t_in, t_out, cost, model, hit_count, expires_at = row
                if expires_at and expires_at < now:
                    conn.execute("DELETE FROM llm_cache WHERE cache_key = ?", (cache_key,))
                    return None

                # Update hit metrics
                conn.execute("UPDATE llm_cache SET hit_count = hit_count + 1 WHERE cache_key = ?", (cache_key,))
                total_tokens = t_in + t_out
                conn.execute(
                    "UPDATE cache_metrics SET total_hits = total_hits + 1, tokens_saved = tokens_saved + ?, usd_saved = usd_saved + ? WHERE id = 1",
                    (total_tokens, cost)
                )

                if is_json:
                    try:
                        return json.loads(resp_text)
                    except Exception:
                        return resp_text
                return resp_text
        except Exception:
            return None

    def set(
        self,
        cache_key: str,
        provider: str,
        model: str,
        response: Any,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        ttl_s: int | None = None,
    ) -> None:
        """Store an LLM response."""
        if not self.is_enabled:
            return
        now = time.time()
        ttl = self.default_ttl_s if ttl_s is None else ttl_s
        expires_at = now + ttl if ttl > 0 else 0.0

        is_json = False
        if isinstance(response, (dict, list)):
            is_json = True
            response_text = json.dumps(response, ensure_ascii=False)
        else:
            response_text = str(response)

        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO llm_cache (
                        cache_key, provider, model, response_text, is_json,
                        tokens_in, tokens_out, cost_usd, created_at, expires_at, hit_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (cache_key, provider, model, response_text, 1 if is_json else 0, tokens_in, tokens_out, cost_usd, now, expires_at))
        except Exception:
            pass

    def get_stats(self) -> dict[str, Any]:
        """Return cache health and cost savings statistics."""
        try:
            with self._get_connection() as conn:
                total_entries = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
                active_entries = conn.execute("SELECT COUNT(*) FROM llm_cache WHERE expires_at > ? OR expires_at = 0", (time.time(),)).fetchone()[0]
                metrics = conn.execute("SELECT total_hits, tokens_saved, usd_saved FROM cache_metrics WHERE id = 1").fetchone()
                return {
                    "enabled": self.is_enabled,
                    "db_path": str(self.db_path),
                    "total_entries": total_entries,
                    "active_entries": active_entries,
                    "total_hits": metrics[0] if metrics else 0,
                    "tokens_saved": metrics[1] if metrics else 0,
                    "usd_saved": round(metrics[2] if metrics else 0.0, 4),
                }
        except Exception as e:
            return {"enabled": self.enabled, "error": str(e)}

    def clear(self, expired_only: bool = False) -> int:
        """Clear cache entries. Returns count of deleted entries."""
        try:
            with self._get_connection() as conn:
                if expired_only:
                    cursor = conn.execute("DELETE FROM llm_cache WHERE expires_at > 0 AND expires_at < ?", (time.time(),))
                else:
                    cursor = conn.execute("DELETE FROM llm_cache")
                return cursor.rowcount
        except Exception:
            return 0


# Shared singleton instance
default_cache = LLMCache()
