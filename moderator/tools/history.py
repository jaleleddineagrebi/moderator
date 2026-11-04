"""Topics already produced, so scheduled runs don't repeat themselves. Committed to the repo by the
GitHub workflow, so it persists between cloud runs."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .. import ROOT

PATH = ROOT / "history" / "topics.jsonl"


def recent(limit: int = 60, path: Path | None = None) -> list[dict]:
    target = path or PATH
    if not target.exists():
        return []
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-limit:]


def record(run_id: str, title: str, angle: str = "", path: Path | None = None) -> None:
    """Record or update the topic chosen for `run_id` (updates in-place if revised within the same run)."""
    target = path or PATH
    entry = {"date": date.today().isoformat(), "run_id": run_id, "title": title, "angle": angle}
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    updated = False
    for i, row in enumerate(rows):
        if row.get("run_id") == run_id:
            rows[i] = entry
            updated = True
            break
    if not updated:
        rows.append(entry)
    target.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
