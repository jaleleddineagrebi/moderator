"""Cost-Optimized LLM Router for Psychology & AI Automation.

Architecture Rules:
1. Pure Logic Tier ($0): Data sanitization, regex, slug creation, keyword deduping,
   and JSON parsing are handled natively in Python without calling an LLM.
2. Lightweight/Free Tier: Keyword extraction, taxonomy classification, and basic
   formatting use local Ollama (Llama-3/Mistral) or ultra-low-cost APIs (Gemini Flash Lite / GPT-4o-mini).
3. Frontier Tier: Complex synthesis, nuanced psychological framing, and cognitive
   bias breakdowns use Gemini Flash / Claude Sonnet / GPT-4o only when necessary.
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
        words = re.findall(r"\b[A-Za-z]{4,}\b", f"{title} {body}".lower())
        freq: dict[str, int] = {}
        for w in words:
            if w not in stopwords:
                freq[w] = freq.get(w, 0) + 1
        return [k for k, _ in sorted(freq.items(), key=lambda item: item[1], reverse=True)[:top_n]]

    @staticmethod
    def safe_json_extract(text: str) -> dict[str, Any]:
        """Robustly extract JSON block from model responses without extra LLM re-prompts."""
        if match := re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
            text = match.group(1)
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start : end + 1])
            raise


class CostOptimizedLLMRouter:
    def __init__(self):
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")

    async def route_and_generate(
        self,
        prompt: str,
        system_prompt: str = "",
        complexity: TaskComplexity = "low",
        json_output: bool = False,
    ) -> LLMResponse:
        """Route prompt based on required complexity to maintain minimum costs."""
        # Route 1: High complexity (Deep synthesis, cognitive bias framing) -> Frontier API
        if complexity == "high":
            if self.gemini_api_key:
                return await self._call_gemini(prompt, system_prompt, model="gemini-2.5-flash", json_output=json_output)
            elif self.openai_api_key:
                return await self._call_openai(prompt, system_prompt, model="gpt-4o", json_output=json_output)

        # Route 2: Low complexity (Drafting, summarization, categorization) -> Ollama local or Flash Lite
        # Try local Ollama first for true $0 cost if running
        ollama_available = await self._check_ollama()
        if ollama_available:
            try:
                return await self._call_ollama(prompt, system_prompt, model="llama3:latest", json_output=json_output)
            except Exception as e:
                logger.warning(f"Local Ollama failed ({e}), falling back to lightweight cloud model")

        # Fallback to lightweight cloud model
        if self.gemini_api_key:
            return await self._call_gemini(prompt, system_prompt, model="gemini-2.5-flash-lite", json_output=json_output)
        elif self.openai_api_key:
            return await self._call_openai(prompt, system_prompt, model="gpt-4o-mini", json_output=json_output)

        raise RuntimeError("No LLM provider available (check OLLAMA_BASE_URL, GEMINI_API_KEY, or OPENAI_API_KEY)")

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
        logger.info(f"Routing to Google Gemini API ({model})")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
        
        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTION: {system}\n\nUSER PROMPT: {prompt}"}]})
        else:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        body: dict[str, Any] = {"contents": contents}
        if json_output:
            body["generationConfig"] = {"responseMimeType": "application/json"}

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            candidate = data["candidates"][0]["content"]["parts"][0]["text"]
            
            # Simple notional cost calculation
            usage = data.get("usageMetadata", {})
            prompt_toks = usage.get("promptTokenCount", 0)
            candidate_toks = usage.get("candidatesTokenCount", 0)
            cost = (prompt_toks * 0.00000015) + (candidate_toks * 0.0000006)

            return LLMResponse(
                content=candidate.strip(),
                model_used=model,
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
