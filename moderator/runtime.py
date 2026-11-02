"""Creates or resumes a run: its folder, shared state and orchestrator."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

from .engine.orchestrator import Orchestrator
from .engine.registry import Registry
from .engine.state import StateStore, new_state


def channel_params(root: Path) -> dict:
    """Saved channel settings (niche, languages, style), written by the niche_discovery workflow."""
    path = root / "channel.yaml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def create_run(registry: Registry, workflow_name: str, overrides: dict) -> Orchestrator:
    wf = registry.workflow(workflow_name)
    params = {**wf.params, **channel_params(registry.root), **overrides}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{stamp}_{re.sub(r'[^a-z0-9_]+', '_', workflow_name.lower())}"
    agents = {s.agent: registry.specs[s.agent].public() for s in wf.steps}
    store = StateStore.create(registry.root / "runs" / run_id, new_state(run_id, wf, params, agents))
    return Orchestrator(store, wf, registry)


def resume_run(registry: Registry, run_dir: Path) -> Orchestrator:
    store = StateStore.load(run_dir)
    return Orchestrator(store, registry.workflow(store.data["workflow"]), registry)
