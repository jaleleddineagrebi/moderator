"""Claude provider: selection per run, complexity routing to Claude models, CLI call and output parsing."""

import asyncio
import json
import subprocess

import pytest

from moderator.engine import llm as llm_mod
from moderator.engine.agent import StepContext
from moderator.engine.llm import GeminiClient, LLMError, create_llm
from moderator.engine.llm_claude import ClaudeCLI
from moderator.engine.state import StateStore, new_state
from moderator.engine.workflow import Step, Workflow

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def make_ctx(tmp_path, params=None, complexity="medium", attempt=1):
    wf = Workflow("w", "W", "", {}, {"max_retries": 0, "max_revision_rounds": 0}, [Step("s1", "x", "S1")])
    store = StateStore.create(tmp_path / "run", new_state("r", wf, params or {}, {}))
    return StepContext(store=store, step_id="s1", attempt=attempt, strategy="default", options={}, config={},
                       complexity=complexity)


def test_provider_selection(tmp_path, monkeypatch):
    monkeypatch.delenv("MODERATOR_LLM", raising=False)
    assert isinstance(create_llm(make_ctx(tmp_path / "a"), {}), GeminiClient)
    assert isinstance(create_llm(make_ctx(tmp_path / "b", {"llm": "claude"}), {}), ClaudeCLI)
    assert isinstance(create_llm(make_ctx(tmp_path / "c"), {"provider": "claude"}), ClaudeCLI)
    monkeypatch.setenv("MODERATOR_LLM", "claude")
    assert isinstance(create_llm(make_ctx(tmp_path / "d"), {}), ClaudeCLI)
    # the run's own choice beats the environment
    assert isinstance(create_llm(make_ctx(tmp_path / "e", {"llm": "gemini"}), {}), GeminiClient)
    with pytest.raises(LLMError):
        create_llm(make_ctx(tmp_path / "f", {"llm": "gpt"}), {})


def test_claude_routing_and_command(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        out = {"subtype": "success", "is_error": False, "structured_output": {"ok": True}, "total_cost_usd": 0.01,
               "duration_ms": 1200, "usage": {"input_tokens": 10, "output_tokens": 5}}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("CLAUDECODE", "1")
    ctx = make_ctx(tmp_path, complexity="low")
    client = ClaudeCLI(ctx, {"binary": "claude"})
    assert asyncio.run(client.ask("hi", schema=SCHEMA, tools=["WebSearch"])) == {"ok": True}
    cmd, kw = calls[-1]
    assert cmd[cmd.index("--model") + 1] == "haiku"
    assert cmd[cmd.index("--effort") + 1] == "low"
    assert cmd[cmd.index("--setting-sources") + 1] == ""  # user settings/CLAUDE.md never leak in
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA
    assert cmd[cmd.index("--allowedTools") + 1] == "WebSearch"
    assert kw["input"] == "hi" and "CLAUDECODE" not in kw["env"]
    assert ctx.store.data["cost"]["total_usd"] == pytest.approx(0.01)

    # retries escalate; a Gemini model name falls back to the routed Claude model
    retry = ClaudeCLI(make_ctx(tmp_path / "r", complexity="medium", attempt=2), {"binary": "claude"})
    asyncio.run(retry.ask("hi", model="flash"))
    cmd, _ = calls[-1]
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert "--json-schema" not in cmd


def test_claude_errors_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1, stdout=json.dumps({"subtype": "error_max_turns", "is_error": True, "result": "boom"}), stderr=""))
    with pytest.raises(LLMError, match="error_max_turns"):
        asyncio.run(ClaudeCLI(make_ctx(tmp_path), {"binary": "claude"}).ask("hi"))
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not logged in"))
    with pytest.raises(LLMError, match="not logged in"):
        asyncio.run(ClaudeCLI(make_ctx(tmp_path / "b"), {"binary": "claude"}).ask("hi"))


def test_claude_images_need_gemini_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        asyncio.run(ClaudeCLI(make_ctx(tmp_path), {}).generate_image("x", tmp_path / "x.png"))
    assert not llm_mod.api_key_available()
