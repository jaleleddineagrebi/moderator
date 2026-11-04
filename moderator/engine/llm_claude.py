"""Claude as the text model, through headless Claude Code (`claude -p`).

Runs on the user's Claude plan: no API key, and the cost Claude Code reports is notional. Selected per run with
`moderator run <workflow> --llm claude` (or `-p llm=claude`, `MODERATOR_LLM=claude`, `config.yaml llm.provider`);
workflows and agents are unchanged. Images still come from Gemini Nano Banana when GEMINI_API_KEY is set,
otherwise agents fall back to stock footage.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .llm import COMPLEXITY_LEVELS, LLMError, escalate

if TYPE_CHECKING:
    from .agent import StepContext

# Same complexity routing as Gemini (agent.yaml `complexity`, one level up per retry), mapped to Claude models
DEFAULT_CLAUDE_TIERS: dict[str, dict[str, str]] = {
    "low": {"model": "haiku", "effort": "low"},       # packaging/SEO, formatting
    "medium": {"model": "sonnet", "effort": "medium"},  # research, QA review
    "high": {"model": "opus", "effort": "high"},       # scriptwriting, niche strategy
}


class ClaudeCLI:
    def __init__(self, ctx: StepContext, config: dict):
        self.ctx = ctx
        self.binary = config.get("binary") or shutil.which("claude") or "claude"
        self.model = config.get("model")  # optional: forces one model for every task
        self.timeout_s = float(config.get("timeout_s", 900))
        self.tiers = {lvl: {**DEFAULT_CLAUDE_TIERS[lvl], **((config.get("tiers") or {}).get(lvl) or {})}
                      for lvl in COMPLEXITY_LEVELS}
        self._gemini_config = config.get("_gemini") or {}
        self._images = None
        # Neutral working folder so calls never pick up this repo's CLAUDE.md
        self.cwd = Path(tempfile.gettempdir()) / "moderator-llm"
        self.cwd.mkdir(exist_ok=True)

    def route(self, complexity: str | None = None) -> tuple[str, str, str]:
        base = complexity or getattr(self.ctx, "complexity", "medium")
        level = escalate(base, int(getattr(self.ctx, "attempt", 1) or 1) - 1)
        tier = self.tiers[level]
        return level, self.model or tier["model"], tier.get("effort") or ""

    def command(self, model: str, effort: str, tools: list[str] | None, system: str | None,
                schema: dict | None) -> list[str]:
        cmd = [self.binary, "-p", "--output-format", "json", "--no-session-persistence",
               "--strict-mcp-config",  # no MCP servers
               "--setting-sources", "",  # none of the user's settings, hooks or CLAUDE.md
               "--model", model, "--tools", ",".join(tools or [])]
        if tools:
            cmd += ["--allowedTools", ",".join(tools)]
        if effort:
            cmd += ["--effort", effort]
        if system:
            cmd += ["--append-system-prompt", system]
        if schema:
            cmd += ["--json-schema", json.dumps(schema)]
        return cmd

    async def ask(self, prompt: str, *, system: str | None = None, schema: dict | None = None,
                  tools: list[str] | None = None, model: str | None = None, complexity: str | None = None,
                  images: list[Path] | None = None) -> Any:
        """Run one prompt. Returns the parsed object when `schema` is given, else the text.
        `images` are opened by Claude with its Read tool (only their folders are made readable)."""
        self.ctx.check_budget()
        extra_dirs: list[str] = []
        if images:
            paths = [str(Path(p).resolve()) for p in images]
            tools = [*(tools or []), "Read"]
            extra_dirs = sorted({str(Path(p).parent) for p in paths})
            prompt += "\n\nImages to inspect (open every one with the Read tool before answering):\n" + "\n".join(paths)
        level, routed_model, effort = self.route(complexity)
        # an explicit Claude model wins; Gemini names ("flash", "gemini-...") fall back to the routed tier
        is_claude_model = bool(model) and (model in ("haiku", "sonnet", "opus") or model.startswith("claude"))
        use_model = model if is_claude_model else routed_model
        cmd = self.command(use_model, effort, tools, system, schema)
        for d in extra_dirs:
            cmd += ["--add-dir", d]
        self.ctx.log(f"Asking Claude ({use_model}, {level} complexity, effort {effort}"
                     + (f", tools: {', '.join(tools)}" if tools else "") + ")")
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
        try:
            proc = await asyncio.to_thread(subprocess.run, cmd, input=prompt, capture_output=True, text=True,
                                           encoding="utf-8", timeout=self.timeout_s, cwd=self.cwd, env=env)
        except FileNotFoundError as e:
            raise LLMError(f"Claude Code CLI not found ({self.binary}). Install it and run `claude` once to log in.") from e
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"claude timed out after {self.timeout_s:.0f}s") from e
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise LLMError(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[-800:]}") from e

        self.ctx.add_cost(float(out.get("total_cost_usd") or 0))  # notional on a Claude plan
        if out.get("is_error") or out.get("subtype") != "success":
            raise LLMError(f"claude error ({out.get('subtype')}): {str(out.get('result'))[:800]}")
        usage = out.get("usage") or {}
        searches = (usage.get("server_tool_use") or {}).get("web_search_requests", 0)
        self.ctx.log(f"Claude answered in {out.get('duration_ms', 0) / 1000:.0f}s "
                     f"(tokens in {usage.get('input_tokens', 0)}, out {usage.get('output_tokens', 0)})"
                     + (f", {searches} web searches" if searches else ""))
        if schema:
            if out.get("structured_output") is None:
                raise LLMError("claude returned no structured output")
            return out["structured_output"]
        return out.get("result", "")

    async def generate_image(self, prompt: str, dest: Path, **kwargs) -> str:
        """Claude has no image model: delegate to Gemini Nano Banana (needs GEMINI_API_KEY)."""
        from .llm import GeminiClient, api_key_available

        if not api_key_available():
            raise LLMError("image generation needs GEMINI_API_KEY (Claude cannot generate images)")
        if self._images is None:
            self._images = GeminiClient(self.ctx, self._gemini_config)
        return await self._images.generate_image(prompt, dest, **kwargs)
