"""Topics already produced, so scheduled runs don't repeat themselves. Committed to the repo by the
GitHub workflow, so it persists between cloud runs."""

from __future__ import annotations

import json
from datetime import date

from .. import ROOT

PATH = ROOT / "history" / "topics.jsonl"


def recent(limit: int = 60) -> list[dict]:
    if not PATH.exists():
        return []
    rows = [json.loads(line) for line in PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-limit:]


def record(run_id: str, title: str, angle: str = "") -> None:
    if any(r["run_id"] == run_id for r in recent(1000)):
        return
    PATH.parent.mkdir(exist_ok=True)
    with PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"date": date.today().isoformat(), "run_id": run_id, "title": title, "angle": angle}, ensure_ascii=False) + "\n")
