"""Publishing a finished youtube_short run: the review summary for a human, and the upload after approval."""

from __future__ import annotations

import json
from pathlib import Path

from .engine.state import StateStore, now_iso
from .tools import youtube_upload
from .tools.languages import normalize_langs

FINAL_CHECKPOINT = "C"


def review_summary(store: StateStore) -> str:
    """Markdown for the approval request (GitHub issue body or console)."""
    d = store.data
    run_dir = store.run_dir
    lines = [f"**Run:** `{d['run_id']}` · status `{d['status']}` · estimated cost ${d['cost']['total_usd']:.2f}", ""]
    failed = [s for s, v in d["steps"].items() if v["status"] == "failed"]
    if failed:
        lines.append(f"❌ Failed steps: {', '.join(failed)}. Last error:")
        err = d["steps"][failed[0]]["errors"][-1]["error"] if d["steps"][failed[0]]["errors"] else "unknown"
        lines += ["```", err[:1500], "```"]
        return "\n".join(lines)
    meta_rel = (d["steps"].get("packaging") or {}).get("outputs", {}).get("metadata")
    if meta_rel and (run_dir / meta_rel).exists():
        meta = json.loads((run_dir / meta_rel).read_text(encoding="utf-8"))
        for lang, m in meta.items():
            lines += [f"### {lang.upper()}: {m['title']}", m["description"], " ".join(m.get("hashtags", [])), ""]
    idea = d["checkpoints"].get("A", {})
    chosen = next((o for o in idea.get("options", []) if o["id"] == idea.get("choice")), None)
    if chosen:
        lines += [f"**Idea:** {chosen['label']}", ""]
    report = run_dir / "qa_report.md"
    if report.exists():
        lines += ["<details><summary>QA report</summary>", "", report.read_text(encoding="utf-8"), "", "</details>"]
    return "\n".join(lines)


def approve_and_upload(store: StateStore, approved_by: str, privacy: str, langs: list[str] | None = None) -> list[dict]:
    """Records the human approval of the final checkpoint, then uploads each language to its channel."""
    d = store.data
    cp = d["checkpoints"][FINAL_CHECKPOINT]
    if cp["status"] == "pending":
        with store.mutate() as s:
            s["checkpoints"][FINAL_CHECKPOINT].update(status="approved", decided_at=now_iso(), comment=f"approved by {approved_by}")
            s["steps"][cp["step"]]["status"] = "done"
            if all(v["status"] == "done" for v in s["steps"].values()):
                s["status"], s["ended_at"] = "done", now_iso()
    elif cp["status"] != "approved":
        raise RuntimeError(f"final checkpoint is '{cp['status']}', not waiting for approval; refusing to upload")

    run_dir = store.run_dir
    qa_out = d["steps"]["qa"]["outputs"]
    meta = json.loads((run_dir / d["steps"]["packaging"]["outputs"]["metadata"]).read_text(encoding="utf-8"))
    target_langs = normalize_langs(langs) if langs else normalize_langs(d["params"].get("languages"))
    results = []
    for lang in target_langs:
        video = run_dir / qa_out[f"video_{lang}"]
        thumb = qa_out.get(f"thumbnail_{lang}")
        res = youtube_upload.upload(lang, video, meta[lang], privacy, Path(run_dir / thumb) if thumb else None)
        results.append({"lang": lang, **res})
        store.notify(f"Uploaded {lang} to '{res['channel']}' as {res['privacy']}: {res['url']}", "success")
    (run_dir / "uploads.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results
