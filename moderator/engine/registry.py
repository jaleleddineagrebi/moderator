"""Discovers agents (agents/<name>/agent.yaml + handler.py) and workflows (workflows/*.yaml)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from .agent import Agent, AgentSpec
from .workflow import Workflow, load_workflow


class Registry:
    def __init__(self, root: Path, config: dict):
        self.root = root
        self.config = config
        self.specs: dict[str, AgentSpec] = {}
        self._instances: dict[str, Agent] = {}
        for spec_file in sorted((root / "agents").glob("*/agent.yaml")):
            raw = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
            name = raw.get("name", spec_file.parent.name)
            self.specs[name] = AgentSpec(**{**raw, "name": name, "folder": spec_file.parent})

    def workflows(self) -> dict[str, Path]:
        return {p.stem: p for p in sorted((self.root / "workflows").glob("*.yaml"))}

    def workflow(self, name: str) -> Workflow:
        path = self.workflows().get(name)
        if not path:
            raise KeyError(f"unknown workflow '{name}' (have: {', '.join(self.workflows())})")
        wf = load_workflow(path)
        missing = {s.agent for s in wf.steps} - set(self.specs)
        if missing:
            raise KeyError(f"workflow '{name}' uses undefined agents: {', '.join(sorted(missing))}")
        return wf

    def agent(self, name: str) -> Agent:
        if name not in self._instances:
            spec = self.specs[name]
            module_spec = importlib.util.spec_from_file_location(f"moderator_agents.{name}", spec.folder / "handler.py")
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            self._instances[name] = module.Handler(spec, self.config)
        return self._instances[name]
