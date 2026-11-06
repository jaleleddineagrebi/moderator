"""Static GitHub Pages exporter for the Moderator Dashboard.

Builds a self-contained static site (`index.html`, `static/styles.css`, `static/app.js`,
`.nojekyll`, `data/runs.json`, and `data/runs/<run_id>/*`) so GitHub Pages displays
live & historical multi-agent progress, outputs, thumbnails, QA reports, Finished Shorts,
and published YouTube links without needing a backend server.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

from . import ROOT
from .config import load_config
from .engine.registry import Registry
from .engine.state import redact
from .engine.state import new_state, now_iso
from .runtime import channel_params

DASHBOARD_DIR = ROOT / "moderator" / "dashboard"
SKIP_DIRS = {"raw", "audio", "sfx", "__pycache__"}
MAX_MEDIA_BYTES = 45 * 1024 * 1024  # 45 MB per file cap (well under GitHub's 100 MB limit)
MEDIA_EXTS = {".mp4", ".webm", ".mov", ".mp3", ".wav", ".m4a", ".ogg"}


def _should_copy_file(rel: Path, *, allow_media: bool) -> bool:
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    name = rel.name
    if name in ("state.json", "music.mp3") or name.startswith("."):
        return False
    # Skip raw per-scene clips (`assets/scene_01.mp4`); keep `contact_sheet.jpg` + `final_short_*.mp4`
    if rel.parts[0] == "assets" and name.startswith("scene_") and rel.suffix.lower() == ".mp4":
        return False
    if rel.suffix.lower() in MEDIA_EXTS and not allow_media:
        return False
    return True


def _filter_outputs_to_existing(outputs: dict[str, Any], dst_run: Path) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, val in (outputs or {}).items():
        if isinstance(val, list):
            kept = [rel for rel in val if isinstance(rel, str) and (dst_run / rel).is_file()]
            if kept:
                cleaned[key] = kept
        elif isinstance(val, str):
            if (dst_run / val).is_file():
                cleaned[key] = val
    return cleaned


def _build_seed_state() -> dict[str, Any]:
    cfg = load_config(ROOT)
    reg = Registry(ROOT, cfg)
    wf = reg.workflow("youtube_short")
    params = {**wf.params, **channel_params(ROOT)}
    agents = {s.agent: reg.specs[s.agent].public() for s in wf.steps}
    seed = new_state("awaiting_first_run", wf, params, agents)
    seed["status"] = "idle"
    seed["is_seed"] = True
    return seed


def export_pages(
    site_dir: Path,
    *,
    repo: str | None = None,
    runs_dir: Path | None = None,
    target_run_id: str | None = None,
    issue_url: str | None = None,
    gh_run_url: str | None = None,
    max_runs: int = 10,
    media_runs: int = 3,
    include_media: bool = True,
) -> dict[str, Any]:
    """Export static dashboard + run snapshots into `site_dir` (e.g. a `gh-pages` checkout)."""
    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")

    repo_slug = (repo or os.environ.get("GITHUB_REPOSITORY") or "").strip()

    # 1. Copy static assets (`static/styles.css`, `static/app.js`) & inject Pages config in `index.html`
    static_out = site_dir / "static"
    static_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DASHBOARD_DIR / "styles.css", static_out / "styles.css")
    shutil.copy2(DASHBOARD_DIR / "app.js", static_out / "app.js")

    pages_cfg = {
        "static_mode": True,
        "repo": repo_slug,
        "actions_url": f"https://github.com/{repo_slug}/actions/workflows/generate-short.yml" if repo_slug else "",
        "issues_url": f"https://github.com/{repo_slug}/issues?q=is%3Aissue+label%3Ashort-review" if repo_slug else "",
    }
    html = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
    inject = f'<script>window.MODERATOR_PAGES = {json.dumps(pages_cfg)};</script>\n  <script src="static/app.js"></script>'
    if '<script src="static/app.js"></script>' in html:
        html = html.replace('<script src="static/app.js"></script>', inject)
    else:
        html = html.replace('<script src="/static/app.js"></script>', inject)
    html = html.replace('href="/static/styles.css"', 'href="static/styles.css"')
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    # 2. Sync runs from `runs_dir` into `site_dir/data/runs/<run_id>` (preserving historical runs in `site_dir`)
    data_runs_dir = site_dir / "data" / "runs"
    data_runs_dir.mkdir(parents=True, exist_ok=True)
    src_runs_root = Path(runs_dir) if runs_dir is not None else (ROOT / "runs")

    if src_runs_root.is_dir():
        for src_run in sorted(src_runs_root.iterdir()):
            state_file = src_run / "state.json"
            if not src_run.is_dir() or not state_file.is_file():
                continue
            try:
                raw_state = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            rid = raw_state.get("run_id") or src_run.name
            dst_run = data_runs_dir / rid
            prev_meta: dict[str, Any] = {}
            if (dst_run / "state.json").is_file():
                try:
                    prev_meta = json.loads((dst_run / "state.json").read_text(encoding="utf-8")).get("pages_meta") or {}
                except Exception:
                    prev_meta = {}
            dst_run.mkdir(parents=True, exist_ok=True)

            for file_path in src_run.rglob("*"):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(src_run)
                if not _should_copy_file(rel, allow_media=include_media):
                    continue
                if file_path.suffix.lower() in MEDIA_EXTS and file_path.stat().st_size > MAX_MEDIA_BYTES:
                    continue
                target = dst_run / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target)

            uploads = prev_meta.get("uploads") or []
            if (src_run / "uploads.json").is_file():
                try:
                    uploads = json.loads((src_run / "uploads.json").read_text(encoding="utf-8"))
                except Exception:
                    pass

            is_target = (target_run_id == rid) or (target_run_id is None)
            meta = {
                **prev_meta,
                "repo": repo_slug or prev_meta.get("repo", ""),
                "exported_at": now_iso(),
                "uploads": uploads,
            }
            if is_target and issue_url:
                meta["issue_url"] = issue_url
            if is_target and gh_run_url:
                meta["gh_run_url"] = gh_run_url

            exported_state = copy.deepcopy(raw_state)
            exported_state["pages_meta"] = meta
            for step in exported_state.get("steps", {}).values():
                step["outputs"] = _filter_outputs_to_existing(step.get("outputs") or {}, dst_run)
            for step in exported_state.get("steps", {}).values():
                for err in step.get("errors") or []:
                    err.pop("trace", None)  # stack traces stay local
            (dst_run / "state.json").write_text(
                redact(json.dumps(exported_state, ensure_ascii=False, indent=2)), encoding="utf-8"
            )

    # 3. Collect all runs in `site_dir/data/runs`, prune oldest beyond `max_runs`, and trim heavy media on older runs
    entries: list[tuple[str, Path, dict[str, Any]]] = []
    for run_folder in data_runs_dir.iterdir():
        sf = run_folder / "state.json"
        if not run_folder.is_dir() or not sf.is_file():
            continue
        try:
            st = json.loads(sf.read_text(encoding="utf-8"))
            sort_key = f"{st.get('started_at') or ''}_{run_folder.name}"
            entries.append((sort_key, run_folder, st))
        except Exception:
            continue

    entries.sort(key=lambda x: x[0], reverse=True)
    kept = entries[:max_runs]
    for _, old_folder, _ in entries[max_runs:]:
        shutil.rmtree(old_folder, ignore_errors=True)

    # Strip large media files from runs beyond the newest `media_runs` so gh-pages stays compact
    for idx, (_, folder, st) in enumerate(kept):
        if idx >= media_runs:
            changed = False
            for f in folder.rglob("*"):
                if f.is_file() and f.suffix.lower() in MEDIA_EXTS:
                    f.unlink(missing_ok=True)
                    changed = True
            if changed:
                for step in st.get("steps", {}).values():
                    step["outputs"] = _filter_outputs_to_existing(step.get("outputs") or {}, folder)
                (folder / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    runs_manifest = []
    for idx, (_, folder, st) in enumerate(kept):
        steps = list((st.get("steps") or {}).values())
        pct = round(sum(100 if s.get("status") == "done" else (s.get("progress") or 0) for s in steps) / len(steps)) if steps else 0
        pm = st.get("pages_meta") or {}
        params = st.get("params") or {}
        runs_manifest.append({
            "run_id": st.get("run_id", folder.name),
            "workflow": st.get("workflow", ""),
            "workflow_title": st.get("workflow_title", st.get("workflow", "")),
            "topic": params.get("topic") or "",
            "status": st.get("status", "unknown"),
            "progress": pct,
            "started_at": st.get("started_at"),
            "ended_at": st.get("ended_at"),
            "cost_usd": round((st.get("cost") or {}).get("total_usd", 0.0), 4),
            "is_live": idx == 0,
            "has_uploads": bool(pm.get("uploads")),
            "issue_url": pm.get("issue_url", ""),
            "gh_run_url": pm.get("gh_run_url", ""),
        })

    live_run_id = runs_manifest[0]["run_id"] if runs_manifest else None
    manifest = {
        "updated_at": now_iso(),
        "repo": repo_slug,
        "live_run_id": live_run_id,
        "runs": runs_manifest,
        "seed_state": _build_seed_state() if not runs_manifest else None,
    }
    (site_dir / "data" / "runs.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
