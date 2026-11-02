"""Loads config.yaml and .env (API keys stay in .env, which is not committed)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from . import ROOT


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(root: Path = ROOT) -> dict:
    load_env(root / ".env")
    path = root / "config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    config = config or {}
    config["root"] = str(root)
    return config
