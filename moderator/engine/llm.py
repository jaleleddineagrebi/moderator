"""Google Gemini client for both reasoning (`flash`) and native image generation (`banana` / Nano Banana).

- Text, structured JSON & Google Search grounding: Gemini Flash (`gemini-3-flash-preview`,
  with automatic fallback to `gemini-2.5-flash`).
- Native 9:16 vertical image generation: Nano Banana (`gemini-3.1-flash-image-preview`,
  with automatic fallback to `gemini-2.5-flash-image`).

Set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) in `.env` or the environment.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from PIL import Image

if TYPE_CHECKING:
    from .agent import StepContext


class LLMError(Exception):
    pass


API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
VERTEX_EXPRESS_V1BETA1 = "https://aiplatform.googleapis.com/v1beta1/publishers/google/models"
VERTEX_EXPRESS_V1 = "https://aiplatform.googleapis.com/v1/publishers/google/models"

# Cache working endpoint, working model, search-tier support, and IPv4 fallback per key
_WORKING_BASE_BY_KEY: dict[str, str] = {}
_WORKING_MODEL_BY_KEY: dict[str, str] = {}
_SEARCH_UNAVAILABLE_KEYS: set[str] = set()
_FORCE_IPV4: bool = False

# Ordered candidate chains so newest -> fallback is automatic across 404 / 429 / 503
TEXT_MODEL_CHAINS: dict[str, list[str]] = {
    "flash": [
        "gemini-3.8-flash",
        "gemini-3-flash-preview",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
    ],
    "flash-lite": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-2.5-flash-lite"],
    "pro": ["gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-3-flash-preview", "gemini-3.8-flash"],
}

IMAGE_MODEL_CHAINS: dict[str, list[str]] = {
    "banana": ["gemini-nano-banana-2.1", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-image", "gemini-2.5-flash-image"],
    "nano-banana": ["gemini-nano-banana-2.1", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-image", "gemini-2.5-flash-image"],
    "nano_banana": ["gemini-nano-banana-2.1", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-image", "gemini-2.5-flash-image"],
    "banana-lite": ["gemini-3.1-flash-lite-image", "gemini-nano-banana-2.1"],
    "banana-pro": ["gemini-3-pro-image", "gemini-nano-banana-2.1", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-image"],
}

# Official Gemini Developer API Paid Tier pricing per 1M tokens (input, output) in USD
TOKEN_PRICING_PER_M: dict[str, tuple[float, float]] = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.25, 1.50),
    "gemini-3-flash": (0.50, 3.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3.1-pro": (2.00, 12.00),
    "gemini-2.5-pro": (1.25, 10.00),
}

# Per-image output cost at 1K resolution (1,120 image tokens)
IMAGE_PRICING_USD: dict[str, float] = {
    "gemini-nano-banana-2.1": 0.0336,       # $30 / 1M image output tokens
    "gemini-3.1-flash-lite-image": 0.0336,  # $30 / 1M image output tokens
    "gemini-3.1-flash-image": 0.0672,       # $60 / 1M image output tokens
    "gemini-2.5-flash-image": 0.0390,
    "gemini-3-pro-image": 0.1340,
}


# The moderator picks the model per task: each agent declares a `complexity` in agent.yaml (low/medium/high),
# a call may override it, and every retry moves one level up. config.yaml `llm.tiers` overrides these defaults.
COMPLEXITY_LEVELS = ["low", "medium", "high"]
DEFAULT_TIERS: dict[str, dict[str, str]] = {
    "low": {"model": "flash-lite", "thinking": "minimal"},   # formatting, metadata, simple checks
    "medium": {"model": "flash", "thinking": "low"},         # research, review
    "high": {"model": "pro", "thinking": "high"},            # creative writing, strategy (falls back to flash)
}
# Retry the same model once after a transient error (503 high demand / per-minute 429) before moving on
TRANSIENT_RETRY_DELAY_S = 2.0
MAX_RETRY_AFTER_S = 60.0
# Models that hit their daily quota or are not enabled, per API key, for the life of this process (= one run)
_EXHAUSTED_MODELS: dict[str, set[str]] = {}


def run_overrides(ctx: Any, setting: str = "thinking") -> dict[str, dict[str, str]]:
    """Per-run model choice by complexity, from the run param `models` (CLI `-p models=...`, GitHub input):
    "high=pro,medium=flash,low=flash-lite", "all=flash", "high=pro:high" (model:thinking or model:effort),
    or a YAML dict {high: pro, low: {model: flash-lite, thinking: minimal}}. Unknown levels are ignored."""
    raw = (getattr(ctx, "params", None) or {}).get("models")
    if not raw:
        return {}
    if isinstance(raw, str):
        raw = dict(part.split("=", 1) for part in re.split(r"[,\s]+", raw.strip()) if "=" in part)
    out: dict[str, dict[str, str]] = {}
    for level, value in raw.items():
        level = str(level).strip().lower()
        if isinstance(value, dict):
            tier = {k: str(v) for k, v in value.items() if v}
        else:
            model, _, extra = str(value).strip().partition(":")
            tier = {"model": model.strip()} | ({setting: extra.strip()} if extra.strip() else {})
        if not tier.get("model") and "model" in tier:
            continue
        for lvl in (COMPLEXITY_LEVELS if level == "all" else [level]):
            if lvl in COMPLEXITY_LEVELS:
                out[lvl] = {**out.get(lvl, {}), **tier}
    return out


def escalate(complexity: str, steps: int) -> str:
    level = complexity if complexity in COMPLEXITY_LEVELS else "medium"
    return COMPLEXITY_LEVELS[min(COMPLEXITY_LEVELS.index(level) + max(steps, 0), len(COMPLEXITY_LEVELS) - 1)]


def thinking_config(model_id: str, level: str | None) -> dict | None:
    """generationConfig.thinkingConfig for a model: Gemini 3 takes a level, Gemini 2.5 a token budget."""
    m = model_id.lower()
    if not level or "image" in m or "banana" in m:
        return None
    if m.startswith("gemini-2.5"):
        budget = {"minimal": 0, "low": 1024, "medium": 4096, "high": -1}.get(level, -1)
        if "pro" in m and budget == 0:
            budget = 128  # 2.5 Pro cannot turn thinking off
        return {"thinkingBudget": budget}
    if "pro" in m:  # Gemini 3 Pro only has low / high
        level = "low" if level in ("minimal", "low") else "high"
    return {"thinkingLevel": level}


def classify_429(resp: httpx.Response) -> tuple[bool, float]:
    """(daily quota exhausted?, suggested retry delay in seconds) from a 429 error body."""
    try:
        details = (resp.json().get("error") or {}).get("details") or []
    except Exception:  # noqa: BLE001 - non-JSON body
        return False, 0.0
    daily, delay = False, 0.0
    for d in details:
        kind = d.get("@type", "")
        if kind.endswith("QuotaFailure"):
            for v in d.get("violations") or []:
                if "perday" in (v.get("quotaId", "") + v.get("quotaMetric", "")).lower():
                    daily = True
        elif kind.endswith("RetryInfo"):
            m = re.match(r"([\d.]+)s", str(d.get("retryDelay", "")))
            if m:
                delay = float(m.group(1))
    return daily, delay


def api_key_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _get_api_key() -> str:
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        raise LLMError("GEMINI_API_KEY is not set. Add `GEMINI_API_KEY=...` to your .env file.")
    return key


def resolve_text_models(requested: str | None) -> list[str]:
    key = (requested or "flash").strip()
    return list(TEXT_MODEL_CHAINS.get(key.lower(), [key]))


def resolve_image_models(requested: str | None) -> list[str]:
    key = (requested or "banana").strip()
    return list(IMAGE_MODEL_CHAINS.get(key.lower(), [key]))


def _estimate_token_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    low = model.lower()
    for prefix, (in_rate, out_rate) in TOKEN_PRICING_PER_M.items():
        if prefix in low:
            return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
    return (input_tokens * 0.30 + output_tokens * 2.50) / 1_000_000


def sanitize_schema_for_gemini(schema: Any) -> Any:
    """Strip JSON Schema keywords (`additionalProperties`) rejected by Gemini's `responseSchema` validator."""
    if isinstance(schema, dict):
        return {k: sanitize_schema_for_gemini(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [sanitize_schema_for_gemini(x) for x in schema]
    return schema


def extract_json(text: str) -> Any:
    """Parse JSON from model text, tolerating markdown code fences or surrounding grounded commentary."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if match:
            return json.loads(match.group(1))
        raise


def _candidate_api_bases(key: str) -> list[str]:
    """Return ordered REST base URLs: Gemini Developer API first (works for both `AIza...`
    and `AQ....` Auth keys), with Vertex AI Express Mode as automatic fallback."""
    explicit = (os.environ.get("GEMINI_API_BASE") or "").strip().rstrip("/")
    if explicit:
        return [explicit]
    order = [API_BASE, VERTEX_EXPRESS_V1BETA1, VERTEX_EXPRESS_V1]
    cached = _WORKING_BASE_BY_KEY.get(key)
    if cached and cached in order:
        return [cached] + [b for b in order if b != cached]
    return order


def _make_async_client(timeout_s: float, ipv4_only: bool) -> httpx.AsyncClient:
    if ipv4_only:
        return httpx.AsyncClient(timeout=timeout_s, transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0"))
    return httpx.AsyncClient(timeout=timeout_s)


class GeminiClient:
    """Unified Gemini Flash (text/JSON/search) + Nano Banana (9:16 image generation) client."""

    def __init__(self, ctx: StepContext, config: dict):
        self.ctx = ctx
        self.model = config.get("model")  # optional: forces one text model for every task
        self.image_model = config.get("image_model", "banana")
        self.timeout_s = float(config.get("timeout_s", 600))
        self.tiers = {lvl: {**DEFAULT_TIERS[lvl], **((config.get("tiers") or {}).get(lvl) or {})} for lvl in COMPLEXITY_LEVELS}

    def route(self, complexity: str | None = None) -> tuple[str, str, str]:
        """(complexity, model alias, thinking level) for this call. Retries escalate one level per attempt."""
        base = complexity or getattr(self.ctx, "complexity", "medium")
        level = escalate(base, int(getattr(self.ctx, "attempt", 1) or 1) - 1)
        tier = {**self.tiers[level], **run_overrides(self.ctx, "thinking").get(level, {})}
        return level, self.model or tier["model"], tier.get("thinking") or ""

    async def _request_once(self, client: httpx.AsyncClient, url: str, headers: dict[str, str], body: dict[str, Any]) -> httpx.Response:
        global _FORCE_IPV4
        try:
            return await client.post(url, headers=headers, json=body)
        except (httpx.ConnectTimeout, httpx.ReadTimeout):
            if _FORCE_IPV4:
                raise
            # Many residential ISPs advertise broken IPv6 routes to googleapis.com; retry over IPv4
            _FORCE_IPV4 = True
            self.ctx.log("Gemini connection timed out on default route; retrying over IPv4", "warning")
            async with _make_async_client(self.timeout_s, ipv4_only=True) as v4_client:
                return await v4_client.post(url, headers=headers, json=body)

    @staticmethod
    def _body_for(body: dict[str, Any], model_id: str, thinking: str | None) -> dict[str, Any]:
        tc = thinking_config(model_id, thinking)
        if not tc:
            return body
        return {**body, "generationConfig": {**(body.get("generationConfig") or {}), "thinkingConfig": tc}}

    async def _call_model(self, client: httpx.AsyncClient, url: str, headers: dict[str, str],
                          body: dict[str, Any], model_id: str, searching: bool) -> httpx.Response:
        """One model, retried once on a transient error (5xx, per-minute 429) or a rejected thinking setting."""
        r = await self._request_once(client, url, headers, body)
        if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in (body.get("generationConfig") or {}):
            self.ctx.log(f"'{model_id}' rejected the thinking setting; retrying without it", "warning")
            gen = {k: v for k, v in body["generationConfig"].items() if k != "thinkingConfig"}
            return await self._request_once(client, url, headers, {**body, "generationConfig": gen})
        if r.status_code in (500, 502, 503, 504):
            self.ctx.log(f"'{model_id}' returned {r.status_code}; retrying once in {TRANSIENT_RETRY_DELAY_S:.0f}s", "warning")
            await asyncio.sleep(TRANSIENT_RETRY_DELAY_S)
            return await self._request_once(client, url, headers, body)
        if r.status_code == 429 and not searching:
            daily, delay = classify_429(r)
            if not daily and 0 < delay <= MAX_RETRY_AFTER_S:
                self.ctx.log(f"'{model_id}' per-minute limit reached; waiting {delay:.0f}s", "warning")
                await asyncio.sleep(delay)
                return await self._request_once(client, url, headers, body)
        return r

    async def _post(self, candidates: list[str], body: dict[str, Any], *, remember_model: bool = False,
                    thinking: str | None = None) -> tuple[str, dict[str, Any]]:
        key = _get_api_key()
        exhausted = _EXHAUSTED_MODELS.setdefault(key, set())
        chain_id = f"{key}|{candidates[0]}"  # remember the working model per chain, so tiers never borrow each other's
        usable = [m for m in candidates if m not in exhausted]
        if not usable:
            raise LLMError(f"Gemini API 429: daily quota used up (or model not enabled) for {', '.join(candidates)}")
        candidates = usable
        if remember_model and _WORKING_MODEL_BY_KEY.get(chain_id) in candidates:
            pref = _WORKING_MODEL_BY_KEY[chain_id]
            candidates = [pref] + [m for m in candidates if m != pref]
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        searching = "tools" in body
        bases = _candidate_api_bases(key)
        last_err = ""
        probe_timeout = min(self.timeout_s, 30.0) if not _FORCE_IPV4 else self.timeout_s
        async with _make_async_client(probe_timeout, ipv4_only=_FORCE_IPV4) as client:
            for b_idx, base in enumerate(bases):
                switch_base = False
                for idx, model_id in enumerate(candidates):
                    r = await self._call_model(client, f"{base}/{model_id}:generateContent", headers,
                                               self._body_for(body, model_id, thinking), model_id, searching)
                    if r.status_code == 200:
                        _WORKING_BASE_BY_KEY[key] = base
                        if remember_model:
                            _WORKING_MODEL_BY_KEY[chain_id] = model_id
                        return model_id, r.json()
                    # Daily quota gone or model not enabled: skip this model for the rest of the run
                    if r.status_code == 404 or (r.status_code == 429 and not searching and classify_429(r)[0]):
                        exhausted.add(model_id)
                        self.ctx.log(f"'{model_id}' is {'not enabled' if r.status_code == 404 else 'out of daily quota'}; "
                                     "skipping it for the rest of this run", "warning")
                    if r.status_code in (404, 429, 500, 502, 503, 504) and idx + 1 < len(candidates):
                        self.ctx.log(f"Model '{model_id}' returned {r.status_code}; falling back to '{candidates[idx + 1]}'",
                                     "warning")
                        continue
                    # If this key belongs to Vertex Express rather than AI Studio, try next base
                    if r.status_code in (400, 401, 403) and b_idx + 1 < len(bases) and (
                        "API_KEY_INVALID" in r.text
                        or "API keys are not supported" in r.text
                        or "UNAUTHENTICATED" in r.text
                        or "PERMISSION_DENIED" in r.text
                    ):
                        last_err = f"Gemini API {r.status_code} ({model_id} @ {base}): {r.text[:600]}"
                        switch_base = True
                        break
                    last_err = f"Gemini API {r.status_code} ({model_id}): {r.text[:800]}"
                    raise LLMError(last_err)
                if not switch_base:
                    break
        raise LLMError(last_err or "No Gemini models succeeded")

    def _charge(self, model_id: str, data: dict) -> str:
        """Add the call's cost (thinking tokens are billed as output) and return a short token summary."""
        usage = data.get("usageMetadata") or {}
        prompt_t = usage.get("promptTokenCount", 0)
        out_t = usage.get("candidatesTokenCount", 0)
        think_t = usage.get("thoughtsTokenCount", 0)
        self.ctx.add_cost(_estimate_token_cost(model_id, prompt_t, out_t + think_t))
        return f"tokens in {prompt_t}, out {out_t}, thinking {think_t}"

    async def ask(self, prompt: str, *, system: str | None = None, schema: dict | None = None,
                  tools: list[str] | None = None, model: str | None = None, complexity: str | None = None,
                  images: list[Path] | None = None) -> Any:
        """Run a Gemini prompt (optionally with JPEG/PNG images to look at). Returns parsed dict when `schema` is provided, else str.
        The model and thinking level follow the task's complexity (agent.yaml, or `complexity=` here);
        an explicit `model=` overrides the routing."""
        self.ctx.check_budget()
        key = _get_api_key()
        level, routed_model, thinking = self.route(complexity)
        candidates = resolve_text_models(model or routed_model)
        requested_search = bool(tools and any(t.lower() in ("websearch", "web_search", "google_search") for t in tools))
        use_search = requested_search and (key not in _SEARCH_UNAVAILABLE_KEYS)

        def _build_body(with_search: bool) -> dict[str, Any]:
            u_prompt = prompt
            g_cfg: dict[str, Any] = {}
            if schema and not with_search:
                g_cfg["responseMimeType"] = "application/json"
                g_cfg["responseSchema"] = sanitize_schema_for_gemini(schema)
            elif schema and with_search:
                u_prompt = (
                    f"{prompt}\n\n"
                    "IMPORTANT: Respond with ONLY a valid JSON object matching this exact JSON Schema "
                    "(no markdown fences, no commentary before or after):\n"
                    f"{json.dumps(schema)}"
                )
            parts: list[dict[str, Any]] = [{"text": u_prompt}]
            for img in images or []:
                mime = "image/png" if Path(img).suffix.lower() == ".png" else "image/jpeg"
                parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(Path(img).read_bytes()).decode("ascii")}})
            b: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}]}
            if system:
                b["systemInstruction"] = {"parts": [{"text": system}]}
            if g_cfg:
                b["generationConfig"] = g_cfg
            if with_search:
                b["tools"] = [{"google_search": {}}]
            return b

        t0 = time.monotonic()
        if use_search:
            self.ctx.log(f"Asking Gemini ({candidates[0]}, {level} complexity, thinking {thinking}, google_search)")
            try:
                # Probe top 2 candidates with google_search so Free Tier (search=429) degrades fast
                used_model, data = await self._post(candidates[:2], _build_body(True), remember_model=True, thinking=thinking)
            except LLMError as err:
                if any(code in str(err) for code in ("429", "403", "400", "503")):
                    _SEARCH_UNAVAILABLE_KEYS.add(key)
                    use_search = False
                    self.ctx.log(
                        "Google Search grounding unavailable on current tier/quota; continuing with Gemini Flash directly",
                        "warning",
                    )
                    used_model, data = await self._post(candidates, _build_body(False), remember_model=True,
                                                        thinking=thinking)
                else:
                    raise
        else:
            self.ctx.log(f"Asking Gemini ({candidates[0]}, {level} complexity, thinking {thinking})")
            used_model, data = await self._post(candidates, _build_body(False), remember_model=True, thinking=thinking)

        tokens = self._charge(used_model, data)

        resp_candidates = data.get("candidates") or []
        if not resp_candidates:
            raise LLMError(f"Gemini returned no candidates: {json.dumps(data)[:600]}")
        cand = resp_candidates[0]
        grounded = bool((cand.get("groundingMetadata") or {}).get("webSearchQueries"))
        self.ctx.log(f"Gemini ({used_model}) answered in {time.monotonic() - t0:.1f}s ({tokens})"
                     + (", grounded with Google Search" if grounded else ""))

        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not schema:
            return text

        try:
            return extract_json(text)
        except Exception:
            if not use_search:
                raise LLMError(f"Gemini JSON parse failed: {text[:500]}")
            # Grounded search occasionally wraps prose; run a fast strict-schema extraction pass without search
            self.ctx.log("Formatting grounded research into strict JSON schema")
            fmt_body: dict[str, Any] = {
                "contents": [{"role": "user", "parts": [{"text": f"Convert the following research into JSON matching the schema:\n\n{text}"}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": sanitize_schema_for_gemini(schema),
                },
            }
            # reformatting is a simple task: always the cheapest tier
            fmt_model, fmt_data = await self._post(resolve_text_models(self.model or self.tiers["low"]["model"]), fmt_body,
                                                   thinking=self.tiers["low"].get("thinking"))
            self._charge(fmt_model, fmt_data)
            fmt_parts = ((fmt_data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            fmt_text = "".join(p.get("text", "") for p in fmt_parts)
            try:
                return extract_json(fmt_text)
            except Exception as e:
                raise LLMError(f"Gemini structured extraction failed: {e}: {fmt_text[:500]}") from e

    async def generate_image(self, prompt: str, dest: Path, *, aspect_ratio: str = "9:16",
                             size: tuple[int, int] | None = (1080, 1920), model: str | None = None) -> str:
        """Generate an image with Nano Banana (`gemini-3.1-flash-image-preview` / `gemini-2.5-flash-image`),
        save it to `dest`, and return the model ID used."""
        self.ctx.check_budget()
        candidates = resolve_image_models(model or self.image_model)
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }
        self.ctx.log(f"Generating {aspect_ratio} image with Nano Banana ({candidates[0]})")
        t0 = time.monotonic()
        used_model, data = await self._post(candidates, body)
        usage = data.get("usageMetadata") or {}
        prompt_cost = (usage.get("promptTokenCount", 150) * 0.50) / 1_000_000
        img_cost = IMAGE_PRICING_USD.get(used_model, 0.0336)
        self.ctx.add_cost(prompt_cost + img_cost)

        resp_candidates = data.get("candidates") or []
        if not resp_candidates:
            raise LLMError(f"Nano Banana returned no candidates: {json.dumps(data)[:600]}")
        parts = (resp_candidates[0].get("content") or {}).get("parts") or []
        raw_bytes: bytes | None = None
        for p in parts:
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                raw_bytes = base64.b64decode(inline["data"])
                break
        if not raw_bytes:
            raise LLMError(f"Nano Banana ({used_model}) returned no image bytes")

        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(io.BytesIO(raw_bytes)) as im:
            rgb = im.convert("RGB")
            if size and rgb.size != size:
                rgb = rgb.resize(size, Image.Resampling.LANCZOS)
            rgb.save(dest)
        self.ctx.log(f"Nano Banana ({used_model}) generated {dest.name} in {time.monotonic() - t0:.1f}s")
        return used_model


PROVIDERS = ("gemini", "claude")


def provider_for(ctx: StepContext, config: dict) -> str:
    """Run param `llm` > env MODERATOR_LLM > config.yaml `llm.provider` > gemini."""
    params = getattr(getattr(ctx, "store", None), "data", {}).get("params", {}) if ctx else {}
    choice = str(params.get("llm") or os.environ.get("MODERATOR_LLM") or config.get("provider") or "gemini").lower()
    if choice not in PROVIDERS:
        raise LLMError(f"unknown llm provider '{choice}' (use one of: {', '.join(PROVIDERS)})")
    return choice


def create_llm(ctx: StepContext, config: dict):
    if provider_for(ctx, config) == "claude":
        from .llm_claude import ClaudeCLI

        return ClaudeCLI(ctx, {**(config.get("claude") or {}), "_gemini": config})
    return GeminiClient(ctx, config)
