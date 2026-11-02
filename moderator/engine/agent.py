"""Agent base class and the context a step runs with."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import StateStore


class BudgetExceeded(Exception):
    pass


@dataclass
class AgentSpec:
    name: str
    title: str
    role: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    # Attempt n runs with strategies[n] (the last one repeats). This is how a retry "changes approach".
    strategies: list[str] = field(default_factory=lambda: ["default"])
    timeout_s: int = 1800
    folder: Path | None = None

    def public(self) -> dict:
        return {k: getattr(self, k) for k in ("name", "title", "role", "inputs", "outputs", "tools", "strategies")}


class Agent:
    """Subclass in agents/<name>/handler.py as `Handler`, and implement run()."""

    def __init__(self, spec: AgentSpec, config: dict):
        self.spec = spec
        self.config = config

    async def run(self, ctx: StepContext) -> dict[str, str]:
        """Do the work. Return {output_name: path relative to the run folder}."""
        raise NotImplementedError


class StepContext:
    def __init__(self, *, store: StateStore, step_id: str, attempt: int, strategy: str,
                 options: dict, config: dict):
        self.store = store
        self.step_id = step_id
        self.attempt = attempt
        self.strategy = strategy
        self.options = options
        self.config = config
        self.run_dir: Path = store.run_dir
        self.revision_requests: list[tuple[str, str]] = []
        self._llm = None

    # Reading shared state

    @property
    def params(self) -> dict:
        return self.store.data["params"]

    @property
    def feedback(self) -> list[dict]:
        """Feedback from the human or QA, oldest first. Address the latest entries when revising."""
        return list(self.store.data["steps"][self.step_id]["feedback"])

    @property
    def previous_errors(self) -> list[dict]:
        return list(self.store.data["steps"][self.step_id]["errors"])

    def revision_notes(self) -> str:
        """Prompt section with feedback to address and errors from earlier attempts ('' if none)."""
        parts = []
        if self.feedback:
            parts.append("FEEDBACK TO ADDRESS (latest last; it overrides earlier instructions):\n"
                         + "\n".join(f"- from {f['from']}: {f['comment']}" for f in self.feedback[-5:]))
        if self.previous_errors:
            parts.append(f"PREVIOUS ATTEMPT FAILED (now using strategy '{self.strategy}'):\n"
                         + "\n".join(f"- {e['error']}" for e in self.previous_errors[-2:]))
        return "\n\n".join(parts)

    @property
    def revision_round(self) -> int:
        return self.store.data["revision_rounds"]

    def upstream(self, step_id: str) -> dict[str, str]:
        """Outputs of another step, as {name: relative path}."""
        return dict(self.store.data["steps"][step_id]["outputs"])

    def decision(self, checkpoint_id: str) -> dict:
        cp = self.store.data["checkpoints"][checkpoint_id]
        return {"choice": cp["choice"], "comment": cp["comment"], "options": cp["options"]}

    def chosen_option(self, checkpoint_id: str) -> dict | None:
        d = self.decision(checkpoint_id)
        return next((o for o in d["options"] if o["id"] == d["choice"]), None)

    # Reporting

    def log(self, msg: str, level: str = "info") -> None:
        self.store.log(self.step_id, msg, level)

    def progress(self, pct: float) -> None:
        self.store.progress(self.step_id, pct)

    def add_cost(self, usd: float) -> None:
        self.store.add_cost(self.step_id, usd)

    def check_budget(self) -> None:
        cost = self.store.data["cost"]
        budget = cost.get("budget_usd")
        if budget and cost["total_usd"] >= budget:
            raise BudgetExceeded(f"budget of ${budget} reached (spent ${cost['total_usd']:.2f})")

    def set_inputs(self, **inputs: Any) -> None:
        with self.store.mutate() as d:
            d["steps"][self.step_id]["inputs"].update(inputs)

    def offer_choices(self, options: list[dict]) -> None:
        """For a 'choice' checkpoint: options are {id, label, detail} dicts shown in the approval panel."""
        cp_id = self.store.data["steps"][self.step_id]["checkpoint"]
        with self.store.mutate() as d:
            d["checkpoints"][cp_id]["options"] = options

    def request_revision(self, step_id: str, feedback: str) -> None:
        """Send another step back for rework (used by reviewers). Applied when this step finishes."""
        self.revision_requests.append((step_id, feedback))

    # Files

    def path(self, rel: str) -> Path:
        p = self.run_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def read_json(self, rel: str) -> Any:
        return json.loads((self.run_dir / rel).read_text(encoding="utf-8"))

    def write_json(self, rel: str, obj: Any) -> str:
        self.path(rel).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return rel

    # Claude

    @property
    def llm(self):
        if self._llm is None:
            from .llm import ClaudeCLI
            self._llm = ClaudeCLI(self, self.config.get("llm", {}))
        return self._llm
