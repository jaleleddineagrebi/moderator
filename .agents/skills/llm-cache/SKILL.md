---
name: llm-cache
description: >-
  Inspect, manage, and optimize LLM token consumption and caching across Gemini, Claude,
  and portal automation pipelines. Use when debugging API costs, checking cache hit rates,
  clearing expired responses, or bypassing cache for non-deterministic tasks.
---

# LLM Caching & Token Optimization Skill

This skill explains how LLM responses are cached across the project to reduce API token consumption, avoid rate limits, eliminate redundant costs, and achieve sub-second response times on repeated calls.

---

## Architecture Overview

The system uses an embedded, deterministic SQLite-backed cache located by default at:
`history/llm_cache.sqlite` (configured via `MODERATOR_CACHE_DIR`).

### Key Features
1. **Deterministic Fingerprint**: Each query is hashed via SHA-256 over:
   - `provider` (`gemini`, `claude`, `router`, etc.)
   - `model` (e.g. `gemini-3.8-flash`, `claude-3-5-sonnet`)
   - `prompt` & `system_instruction`
   - `json_schema` & `tools`
   - `images` (content MD5 digests)
   - `json_output` mode
2. **Token & Dollar Accounting**:
   - Every cache hit logs `0 tokens consumed, $0.00 cost`.
   - The cache records cumulative saved input tokens, output tokens, and USD savings.
3. **Automatic TTL**:
   - Entries default to 7 days (604,800 seconds). Configurable via `MODERATOR_LLM_CACHE_TTL`.
   - Expired entries are automatically evicted upon access or via maintenance commands.

---

## CLI Management Commands

### Check Cache Statistics & Financial Savings
```sh
uv run python -m moderator cache-stats
```
Output preview:
```
LLM Response Cache Statistics:
  Status:         Enabled
  Database Path:  history/llm_cache.sqlite
  Total Entries:  42
  Active Entries: 42
  Cache Hits:     18
  Tokens Saved:   124,530
  Cost Saved:     $0.1865
```

### Clear Cache Entries
To clear only expired entries:
```sh
uv run python -m moderator cache-clear --expired-only
```

To purge all cached responses:
```sh
uv run python -m moderator cache-clear
```

---

## In-Code Usage & Controls

### 1. Engine Workflows (Gemini & Claude)
All agent calls through `ctx.llm.ask(...)` use caching by default.
To force a fresh generation (e.g. for diverse creative generation):
```python
# Force fresh generation, bypassing cache
result = await ctx.llm.ask(prompt, cache=False)
```

### 2. Portal Daily Content Automation
The router in `portal/automation/llm_router.py` automatically checks and updates the cache:
```python
res = await router.route_and_generate(prompt, system_prompt, complexity="low", cache=True)
```

### 3. Global Environment Overrides
- **Disable Caching Completely**: Set `MODERATOR_LLM_CACHE=0` (or `false` / `no`).
- **Custom Cache TTL**: Set `MODERATOR_LLM_CACHE_TTL=86400` (e.g. 24 hours).
- **Custom Cache Folder**: Set `MODERATOR_CACHE_DIR=/path/to/cache`.

---

## Best Practices for Prompt Prefixing (Gemini Implicit Caching)
To maximize both local cache hits and Google Gemini's server-side implicit context caching:
1. **Keep System Instructions Static**: Avoid interpolating timestamps, random nonces, or dynamic counters into `systemInstruction`.
2. **Put Dynamic Data in User Prompts**: Pass dates, run IDs, or transient data inside the user prompt rather than the system prompt.
3. **Use Canonical JSON Schemas**: Sort and declare fixed properties in `schema` so fingerprints remain identical across runs.
