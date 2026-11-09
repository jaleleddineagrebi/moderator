"""Cost-Optimized Multi-Provider LLM Router for Psychology & AI Automation.

Architecture Rules:
1. Pure Logic Tier ($0): Data sanitization, regex, slug creation, keyword deduping,
   and JSON parsing are handled natively in Python without calling an LLM.
2. Cross-Provider Fallback Cascade:
   - Primary: Google Gemini, cheapest tier only (the Flash-Lite models).
   - Secondary: Anthropic Claude (claude-3-5-haiku, the cheapest Claude).
   - Tertiary: OpenAI (gpt-4o-mini, the cheapest GPT).
   - Quaternary: Groq (llama-3.3-70b-versatile).
   - Local: Ollama (llama3) if running locally for $0.
3. Cost rule: ALWAYS the cheapest model of each provider. `complexity` is accepted for compatibility but
   never selects a more expensive model, and fallbacks never move up to a pricier tier.
4. Automatic Failover: If any provider is rate-limited (429), quota-depleted, or 404s,
   the router logs the event and automatically cascades to the next available provider.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("LLMRouter")

TaskComplexity = Literal["trivial", "low", "high"]

# Cheapest model of each provider, cheapest first. Nothing here ever escalates to a pricier model.
GEMINI_CHEAPEST = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]
ANTHROPIC_CHEAPEST = "claude-3-5-haiku-20241022"
OPENAI_CHEAPEST = "gpt-4o-mini"
GROQ_CHEAPEST = "llama-3.3-70b-versatile"
# USD per 1M tokens (input, output); unknown Lite models use the higher Lite price
GEMINI_LITE_PRICES = {"gemini-2.5-flash-lite": (0.10, 0.40)}
GEMINI_LITE_DEFAULT_PRICE = (0.25, 1.50)
REQUEST_TIMEOUT_S = 90.0


@dataclass
class LLMResponse:
    content: str
    model_used: str
    estimated_cost_usd: float
    raw_tokens: dict[str, int]


class NativeOptimizer:
    """Tier 0: Pure Python tasks that must never consume LLM budget ($0.000)."""

    @staticmethod
    def slugify(text: str) -> str:
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
        return re.sub(r"[-\s]+", "-", text)[:80]

    @staticmethod
    def clean_html_and_boilerplate(raw_text: str) -> str:
        clean = re.sub(r"<[^>]+>", " ", raw_text)
        clean = re.sub(r"http\S+|www\.\S+", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def extract_keywords_heuristics(title: str, body: str, top_n: int = 5) -> list[str]:
        """Fast heuristic keyword extraction before or instead of calling an LLM."""
        stopwords = {
            "the", "and", "in", "to", "of", "a", "with", "for", "is", "on", "that", "this",
            "are", "as", "by", "from", "at", "it", "an", "be", "how", "why", "what", "their"
        }
        words = re.findall(r"\b[a-z]{4,}\b", (title + " " + body).lower())
        meaningful = [w for w in words if w not in stopwords]
        counts: dict[str, int] = {}
        for w in meaningful:
            counts[w] = counts.get(w, 0) + 1
        return sorted(counts.keys(), key=lambda k: counts[k], reverse=True)[:top_n]

    @staticmethod
    def safe_json_extract(text: str) -> dict[str, Any]:
        """Robust parser that strips markdown fences and trailing text."""
        cleaned = re.sub(r"```json\s*", "", text)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                return json.loads(cleaned[start : end + 1])
            raise


class CostOptimizedLLMRouter:
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    async def route_and_generate(
        self,
        prompt: str,
        system_prompt: str = "",
        complexity: TaskComplexity = "low",
        json_output: bool = False,
        cache: bool = True,
    ) -> LLMResponse:
        """Route prompt through available LLM providers with automatic cross-provider fallback."""
        try:
            from moderator.engine.llm_cache import default_cache
        except Exception:
            default_cache = None

        # The cache is only an optimisation: any cache problem must never fail a generation
        cache_key = ""
        if cache and default_cache:
            try:
                cache_key = default_cache.compute_key(
                    provider="router",
                    model="cheapest",  # the router always uses the cheapest model, whatever `complexity` says
                    prompt=prompt,
                    system=system_prompt,
                    json_output=json_output,
                )
                cached_val = default_cache.get(cache_key)
                if cached_val is not None:
                    logger.info("LLMRouter: CACHE HIT! Reusing previously synthesized output (0 API tokens, $0.00 cost)")
                    return LLMResponse(
                        content=cached_val if isinstance(cached_val, str) else json.dumps(cached_val),
                        model_used="cache",
                        estimated_cost_usd=0.0,
                        raw_tokens={},
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"LLMRouter: cache lookup skipped ({type(e).__name__}: {e})")
                cache_key = ""

        errors: list[str] = []

        def _remember(resp: LLMResponse) -> LLMResponse:
            if cache and default_cache and cache_key:
                try:
                    if json_output:
                        NativeOptimizer.safe_json_extract(resp.content)  # never cache an answer that cannot be parsed
                    default_cache.set(
                        cache_key=cache_key,
                        provider="router",
                        model=resp.model_used,
                        response=resp.content,
                        tokens_in=int(resp.raw_tokens.get("promptTokenCount") or resp.raw_tokens.get("input_tokens")
                                      or resp.raw_tokens.get("prompt_tokens") or 0),
                        tokens_out=int(resp.raw_tokens.get("candidatesTokenCount") or resp.raw_tokens.get("output_tokens")
                                       or resp.raw_tokens.get("completion_tokens") or 0),
                        cost_usd=resp.estimated_cost_usd,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"LLMRouter: could not cache the response ({type(e).__name__}: {e})")
            return resp

        # 1. Primary Provider: Google Gemini (Active modern models)
        if self.gemini_api_key:
            try:
                return _remember(await self._call_gemini(prompt, system_prompt, model=GEMINI_CHEAPEST[0], json_output=json_output))
            except Exception as e:
                msg = f"Gemini provider failed: {type(e).__name__}: {e}"
                logger.warning(f"{msg}. Falling back to next available LLM provider...")
                errors.append(msg)

        # 2. Secondary Provider: Anthropic Claude
        if self.anthropic_api_key:
            try:
                return _remember(await self._call_anthropic(prompt, system_prompt, model=ANTHROPIC_CHEAPEST, json_output=json_output))
            except Exception as e:
                msg = f"Anthropic provider failed: {type(e).__name__}: {e}"
                logger.warning(f"{msg}. Falling back to next available LLM provider...")
                errors.append(msg)

        # 3. Tertiary Provider: OpenAI
        if self.openai_api_key:
            try:
                return _remember(await self._call_openai(prompt, system_prompt, model=OPENAI_CHEAPEST, json_output=json_output))
            except Exception as e:
                msg = f"OpenAI provider failed: {type(e).__name__}: {e}"
                logger.warning(f"{msg}. Falling back to next available LLM provider...")
                errors.append(msg)

        # 4. Quaternary Provider: Groq
        if self.groq_api_key:
            try:
                return _remember(await self._call_groq(prompt, system_prompt, model=GROQ_CHEAPEST, json_output=json_output))
            except Exception as e:
                msg = f"Groq provider failed: {type(e).__name__}: {e}"
                logger.warning(f"{msg}. Falling back to local Ollama...")
                errors.append(msg)

        # 5. Local Fallback: Ollama ($0)
        ollama_available = await self._check_ollama()
        if ollama_available:
            try:
                return _remember(await self._call_ollama(prompt, system_prompt, model="llama3:latest", json_output=json_output))
            except Exception as e:
                msg = f"Local Ollama failed: {e}"
                errors.append(msg)

        error_summary = "\n- ".join(errors) if errors else "No LLM API keys configured."
        raise RuntimeError(f"All LLM providers failed or exhausted quota:\n- {error_summary}")

    async def _check_ollama(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                res = await client.get(f"{self.ollama_base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def _call_ollama(self, prompt: str, system: str, model: str, json_output: bool) -> LLMResponse:
        logger.info(f"Routing to local Ollama ({model}) - $0 cost")
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
        }
        if json_output:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.ollama_base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return LLMResponse(
                content=data.get("response", "").strip(),
                model_used=f"ollama/{model}",
                estimated_cost_usd=0.0,
                raw_tokens={"eval_count": data.get("eval_count", 0)},
            )

    async def _call_gemini(self, prompt: str, system: str, model: str, json_output: bool) -> LLMResponse:
        candidates = [model]  # fallbacks stay on the cheapest (Flash-Lite) tier, never a pricier Flash/Pro
        candidates += [m for m in GEMINI_CHEAPEST if m not in candidates]

        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTION: {system}\n\nUSER PROMPT: {prompt}"}]})
        else:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        body: dict[str, Any] = {"contents": contents}
        if json_output:
            body["generationConfig"] = {"responseMimeType": "application/json"}

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
            for cand_model in candidates:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:generateContent?key={self.gemini_api_key}"
                try:
                    logger.info(f"Routing to Google Gemini API ({cand_model})")
                    resp = await client.post(url, json=body)
                    if resp.status_code in (429, 404, 500, 502, 503, 504):
                        logger.warning(
                            f"Gemini model '{cand_model}' returned HTTP {resp.status_code} ({resp.text[:120]}); falling back to next available model..."
                        )
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    candidate = data["candidates"][0]["content"]["parts"][0]["text"]

                    # Notional cost calculation
                    usage = data.get("usageMetadata", {})
                    prompt_toks = usage.get("promptTokenCount", 0)
                    candidate_toks = usage.get("candidatesTokenCount", 0)
                    in_price, out_price = GEMINI_LITE_PRICES.get(cand_model, GEMINI_LITE_DEFAULT_PRICE)
                    cost = (prompt_toks * in_price + candidate_toks * out_price) / 1_000_000

                    return LLMResponse(
                        content=candidate.strip(),
                        model_used=cand_model,
                        estimated_cost_usd=round(cost, 6),
                        raw_tokens=usage,
                    )
                except httpx.HTTPError as e:
                    last_error = e
                    logger.warning(f"Error calling '{cand_model}': {type(e).__name__}: {e}. Trying fallback model...")

        if last_error:
            raise last_error
        raise RuntimeError("All Gemini candidate models failed or returned 404/429.")

    async def _call_anthropic(self, prompt: str, system: str, model: str, json_output: bool) -> LLMResponse:
        logger.info(f"Routing to Anthropic API ({model})")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        user_prompt = prompt
        if json_output:
            user_prompt = f"{prompt}\n\nIMPORTANT: Respond with ONLY a valid raw JSON object (no markdown code blocks, no other text)."

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if system:
            body["system"] = system

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["content"][0]["text"]
            usage = data.get("usage", {})
            in_toks = usage.get("input_tokens", 0)
            out_toks = usage.get("output_tokens", 0)
            cost = (in_toks * 0.0000008) + (out_toks * 0.000004)  # Claude 3.5 Haiku
            return LLMResponse(
                content=content.strip(),
                model_used=f"anthropic/{model}",
                estimated_cost_usd=round(cost, 6),
                raw_tokens=usage,
            )

    async def _call_openai(self, prompt: str, system: str, model: str, json_output: bool) -> LLMResponse:
        logger.info(f"Routing to OpenAI API ({model})")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {"model": model, "messages": messages}
        if json_output:
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            cost = 0.00015 if "mini" in model else 0.003
            return LLMResponse(
                content=content.strip(),
                model_used=model,
                estimated_cost_usd=cost,
                raw_tokens=usage,
            )

    async def _call_groq(self, prompt: str, system: str, model: str, json_output: bool) -> LLMResponse:
        logger.info(f"Routing to Groq API ({model})")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"}

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {"model": model, "messages": messages}
        if json_output:
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return LLMResponse(
                content=content.strip(),
                model_used=f"groq/{model}",
                estimated_cost_usd=0.0001,
                raw_tokens=usage,
            )
