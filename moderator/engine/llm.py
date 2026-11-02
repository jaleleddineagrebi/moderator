"""Claude access through headless Claude Code (`claude -p`).

This runs on the user's existing Claude plan, so there is no API key and no per-token bill.
The cost Claude Code reports is recorded as a notional figure for the dashboard.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import StepContext


class LLMError(Exception):
    pass


class ClaudeCLI:
    def __init__(self, ctx: StepContext, config: dict):
        self.ctx = ctx
        self.binary = config.get("binary") or shutil.which("claude") or "claude"
        self.model = config.get("model", "opus")
        self.effort = config.get("effort")
        self.timeout_s = config.get("timeout_s", 900)
        # Neutral working folder so the call doesn't pick up this repo's CLAUDE.md.
        self.cwd = Path(tempfile.gettempdir()) / "moderator-llm"
        self.cwd.mkdir(exist_ok=True)

    async def ask(self, prompt: str, *, system: str | None = None, schema: dict | None = None,
                  tools: list[str] | None = None, model: str | None = None) -> Any:
        """Run one prompt. Returns the parsed object when `schema` is given, else the text."""
        self.ctx.check_budget()
        cmd = [self.binary, "-p", "--output-format", "json", "--no-session-persistence",
               "--strict-mcp-config", "--model", model or self.model, "--tools", ",".join(tools or [])]
        if tools:
            cmd += ["--allowedTools", ",".join(tools)]
        if system:
            cmd += ["--append-system-prompt", system]
        if schema:
            cmd += ["--json-schema", json.dumps(schema)]
        if self.effort:
            cmd += ["--effort", self.effort]

        self.ctx.log(f"Asking Claude ({model or self.model}{', tools: ' + ', '.join(tools) if tools else ''})")
        proc = await asyncio.to_thread(
            subprocess.run, cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
            timeout=self.timeout_s, cwd=self.cwd,
        )
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise LLMError(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[-800:]}")

        self.ctx.add_cost(float(out.get("total_cost_usd") or 0))
        if out.get("is_error") or out.get("subtype") != "success":
            raise LLMError(f"claude error ({out.get('subtype')}): {str(out.get('result'))[:800]}")
        searches = (out.get("usage") or {}).get("server_tool_use", {}).get("web_search_requests", 0)
        self.ctx.log(f"Claude answered in {out.get('duration_ms', 0) / 1000:.0f}s"
                     + (f", {searches} web searches" if searches else ""))
        if schema:
            if out.get("structured_output") is None:
                raise LLMError("claude returned no structured output")
            return out["structured_output"]
        return out.get("result", "")
