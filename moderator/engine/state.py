"""The run's shared state: the single source of truth, persisted to state.json.

Only the engine process writes the file. Agents and the dashboard go through this
store, so parallel steps never race on the file.
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .workflow import Workflow

# Error messages from httpx include the request URL, and some APIs (Pixabay) only accept the key as a query
# parameter. state.json is published (gh-pages, Actions artifacts, review issues), so secrets are scrubbed on save.
SECRET_ENV_PREFIXES = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "PIXABAY_API_KEY", "PEXELS_API_KEY", "YOUTUBE_API_KEY",
                       "YOUTUBE_TOKEN")
_KEY_PARAM = re.compile(r"([?&](?:key|api_key|apikey|access_token|token)=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: str) -> str:
    """Remove API keys and tokens from text that may be published."""
    text = _KEY_PARAM.sub(lambda m: m.group(1) + "***", text)
    for name, value in os.environ.items():
        if name.startswith(SECRET_ENV_PREFIXES) and len(value) >= 8:
            text = text.replace(value, "***")
            text = text.replace(json.dumps(value)[1:-1], "***")  # same value as escaped inside JSON
    return text

STATUSES = ("queued", "running", "waiting_for_approval", "done", "failed", "needs_revision")
MAX_LOGS_PER_STEP = 500


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_state(run_id: str, workflow: Workflow, params: dict, agents: dict) -> dict:
    steps = {}
    checkpoints = {}
    for s in workflow.steps:
        steps[s.id] = {
            "title": s.title,
            "agent": s.agent,
            "depends_on": s.depends_on,
            "checkpoint": s.checkpoint.id if s.checkpoint else None,
            "status": "queued",
            "progress": 0,
            "started_at": None,
            "ended_at": None,
            "attempt": 0,
            "retries": 0,
            "max_retries": workflow.settings["max_retries"],
            "strategy": None,
            "inputs": {},
            "outputs": {},
            "logs": [],
            "errors": [],
            "feedback": [],
            "cost_usd": 0.0,
        }
        if s.checkpoint:
            checkpoints[s.checkpoint.id] = {
                "title": s.checkpoint.title,
                "type": s.checkpoint.type,
                "step": s.id,
                "route_to": s.checkpoint.route_to or s.id,
                "status": "idle",  # idle -> pending -> approved | changes_requested
                "options": [],
                "choice": None,
                "comment": None,
                "decided_at": None,
            }
    return {
        "run_id": run_id,
        "workflow": workflow.name,
        "workflow_title": workflow.title,
        "status": "running",
        "params": params,
        "started_at": now_iso(),
        "ended_at": None,
        "revision_rounds": 0,
        "cost": {"total_usd": 0.0, "budget_usd": params.get("budget_usd"), "by_agent": {}},
        "agents": agents,
        "pipeline": {"depth": workflow.depth()},
        "steps": steps,
        "checkpoints": checkpoints,
        "notifications": [],
    }


class StateStore:
    def __init__(self, path: Path, data: dict):
        self.path = path.resolve()
        self.data = data
        self._lock = threading.RLock()

    @classmethod
    def create(cls, run_dir: Path, data: dict) -> StateStore:
        run_dir.mkdir(parents=True, exist_ok=True)
        store = cls(run_dir / "state.json", data)
        store.save()
        return store

    @classmethod
    def load(cls, run_dir: Path) -> StateStore:
        path = run_dir / "state.json"
        return cls(path, json.loads(path.read_text(encoding="utf-8")))

    @property
    def run_dir(self) -> Path:
        return self.path.parent

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.data)

    @contextmanager
    def mutate(self):
        """Lock, let the caller change self.data, then persist."""
        with self._lock:
            yield self.data
            self.save()

    def save(self) -> None:
        with self._lock:
            text = redact(json.dumps(self.data, ensure_ascii=False, indent=2))
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(text, encoding="utf-8")
            for attempt in range(5):
                try:
                    os.replace(tmp, self.path)
                    return
                except PermissionError:  # Windows: a reader briefly holds the file open
                    time.sleep(0.05 * (attempt + 1))
            os.replace(tmp, self.path)

    # Convenience writers used by agents through StepContext

    def log(self, step_id: str, msg: str, level: str = "info") -> None:
        with self.mutate() as d:
            logs = d["steps"][step_id]["logs"]
            logs.append({"ts": now_iso(), "level": level, "msg": msg})
            del logs[:-MAX_LOGS_PER_STEP]

    def progress(self, step_id: str, pct: float) -> None:
        with self.mutate() as d:
            d["steps"][step_id]["progress"] = max(0, min(100, round(pct)))

    def add_cost(self, step_id: str, usd: float) -> None:
        with self.mutate() as d:
            step = d["steps"][step_id]
            step["cost_usd"] = round(step["cost_usd"] + usd, 6)
            cost = d["cost"]
            cost["total_usd"] = round(cost["total_usd"] + usd, 6)
            cost["by_agent"][step["agent"]] = round(cost["by_agent"].get(step["agent"], 0) + usd, 6)

    def notify(self, msg: str, level: str = "info", step: str | None = None) -> None:
        with self.mutate() as d:
            d["notifications"].append({"ts": now_iso(), "level": level, "msg": msg, "step": step})
