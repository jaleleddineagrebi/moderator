"""Workflow definitions: a YAML file listing steps, their agents, dependencies and checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class WorkflowError(Exception):
    pass


@dataclass
class Checkpoint:
    id: str
    title: str
    type: str = "approve"  # "approve" or "choice" (pick one of the options the agent offered)
    route_to: str | None = None  # step that receives "request changes" feedback; defaults to the step itself


@dataclass
class Step:
    id: str
    agent: str
    title: str
    depends_on: list[str] = field(default_factory=list)
    checkpoint: Checkpoint | None = None
    options: dict = field(default_factory=dict)  # free-form settings passed to the agent as ctx.options


@dataclass
class Workflow:
    name: str
    title: str
    description: str
    params: dict
    settings: dict
    steps: list[Step]

    @property
    def step_map(self) -> dict[str, Step]:
        return {s.id: s for s in self.steps}

    def downstream(self, step_id: str) -> list[str]:
        """Every step that directly or transitively depends on step_id, in workflow order."""
        hit = {step_id}
        for s in self.steps:  # steps are kept topologically sorted
            if any(d in hit for d in s.depends_on):
                hit.add(s.id)
        hit.discard(step_id)
        return [s.id for s in self.steps if s.id in hit]

    def depth(self) -> dict[str, int]:
        d: dict[str, int] = {}
        for s in self.steps:
            d[s.id] = 1 + max((d[p] for p in s.depends_on), default=-1)
        return d


def load_workflow(path: Path) -> Workflow:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    steps = []
    for item in raw.get("steps", []):
        cp = item.get("checkpoint")
        steps.append(Step(
            id=item["id"],
            agent=item["agent"],
            title=item.get("title", item["id"]),
            depends_on=list(item.get("depends_on", [])),
            checkpoint=Checkpoint(**cp) if cp else None,
            options=item.get("with", {}) or {},
        ))
    raw_ids = [s.id for s in steps]
    if len(raw_ids) != len(set(raw_ids)):
        raise WorkflowError("duplicate step ids")
    wf = Workflow(
        name=raw.get("name", path.stem),
        title=raw.get("title", path.stem),
        description=raw.get("description", ""),
        params=raw.get("params", {}) or {},
        settings={"max_retries": 2, "max_revision_rounds": 2, "retry_backoff_s": 0.0, **(raw.get("settings") or {})},
        steps=_toposort(steps),
    )
    _validate(wf)
    return wf


def _toposort(steps: list[Step]) -> list[Step]:
    ids = {s.id for s in steps}
    for s in steps:
        for d in s.depends_on:
            if d not in ids:
                raise WorkflowError(f"step '{s.id}' depends on unknown step '{d}'")
    done: list[Step] = []
    placed: set[str] = set()
    pending = list(steps)
    while pending:
        ready = [s for s in pending if all(d in placed for d in s.depends_on)]
        if not ready:
            raise WorkflowError("dependency cycle between: " + ", ".join(s.id for s in pending))
        for s in ready:
            done.append(s)
            placed.add(s.id)
            pending.remove(s)
    return done


def _validate(wf: Workflow) -> None:
    ids = [s.id for s in wf.steps]
    if len(ids) != len(set(ids)):
        raise WorkflowError("duplicate step ids")
    cps = [s.checkpoint.id for s in wf.steps if s.checkpoint]
    if len(cps) != len(set(cps)):
        raise WorkflowError("duplicate checkpoint ids")
    for s in wf.steps:
        if s.checkpoint:
            if s.checkpoint.type not in ("approve", "choice"):
                raise WorkflowError(f"checkpoint {s.checkpoint.id}: unknown type '{s.checkpoint.type}'")
            target = s.checkpoint.route_to
            if target and target != s.id and s.id not in wf.downstream(target):
                raise WorkflowError(f"checkpoint {s.checkpoint.id}: route_to '{target}' is not upstream of '{s.id}'")
