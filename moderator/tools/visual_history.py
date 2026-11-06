"""Visual history tracking to ensure cross-run visual diversity.

Keeps a persistent log of visuals (stock video pages, stock photos, AI prompts)
already used in previous Shorts so that future runs do not reuse the same footage.
Committed alongside topic history.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .. import ROOT

PATH = ROOT / "history" / "visuals.jsonl"


def recent_used_pages(limit: int = 300, path: Path | None = None) -> set[str]:
    """Return a set of page URLs and query identifiers used in recent Shorts."""
    target = path or PATH
    if not target.exists():
        return set()
    used: set[str] = set()
    try:
        lines = [line.strip() for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines[-limit:]:
            data = json.loads(line)
            page = data.get("page")
            if page:
                used.add(page)
    except Exception:
        pass
    return used


def record_visuals(run_id: str, licenses: list[dict], path: Path | None = None) -> None:
    """Record visuals chosen for a Short run so future runs avoid repeating them."""
    target = path or PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    new_entries = []
    for lic in licenses:
        page = lic.get("page")
        if not page:
            continue
        new_entries.append({
            "date": today,
            "run_id": run_id,
            "scene": lic.get("scene", ""),
            "provider": lic.get("provider", ""),
            "page": page,
            "query": lic.get("query", ""),
        })

    if not new_entries:
        return

    existing_rows = []
    if target.exists():
        try:
            existing_rows = [
                json.loads(line)
                for line in target.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception:
            existing_rows = []

    # Update or append
    existing_rows = [r for r in existing_rows if r.get("run_id") != run_id]
    existing_rows.extend(new_entries)

    target.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in existing_rows) + "\n",
        encoding="utf-8",
    )
