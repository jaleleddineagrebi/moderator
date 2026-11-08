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
        step_name = failed[0]
        step_data = d["steps"][step_name]
        err = step_data["errors"][-1]["error"] if step_data.get("errors") else "unknown"
        spent = d.get("cost", {}).get("total_usd", 0.0)
        budget = d.get("params", {}).get("budget_usd") or d.get("cost", {}).get("budget_usd")
        
        lines.append(f"## ❌ Step '{step_name}' Failed")
        
        # 1. Budget Exceeded
        if "budget of" in err.lower() or "budgetexceeded" in err.lower():
            lines += [
                "",
                "> [!WARNING]",
                f"> **Safety Spend Cap Exceeded:** Spent ${spent:.2f} (budget cap was ${budget}).",
                "> ",
                "> **Resolution:** Re-run with a higher spend cap using `-p budget_usd=2.50` or adjust `INPUT_BUDGET` in GitHub Actions. Free tier Gemini API keys pay $0.00.",
                ""
            ]
        # 2. Rate Limit (429) or Quota Exhaustion
        elif "429" in err or "quota" in err.lower() or "exhausted" in err.lower() or "rate limit" in err.lower():
            lines += [
                "",
                "> [!CAUTION]",
                "> **API Rate Limit / Quota Exhausted:** Candidate models exhausted their request limits or daily quota.",
                "> ",
                f"> **Current Spent:** ${spent:.2f}",
                "> **Resolution:** The engine automatically cascades through fallback models. If all models are exhausted, wait for the per-minute or daily quota reset, or verify your API keys at Google AI Studio.",
                ""
            ]

        lines += ["### Error Traceback", "```text", err[:1800], "```"]
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


def upload_tiktok(store: StateStore, privacy: str, langs: list[str] | None = None) -> list[dict]:
    """Posts the already-approved run to TikTok. Refuses unless checkpoint C was approved (by approve_and_upload
    or the `Upload Short` workflow), so nothing reaches TikTok without a human decision."""
    from .tools import tiktok_upload

    d = store.data
    if d["checkpoints"][FINAL_CHECKPOINT]["status"] != "approved":
        raise RuntimeError("final checkpoint is not approved; refusing to post to TikTok")
    run_dir = store.run_dir
    qa_out = d["steps"]["qa"]["outputs"]
    meta = json.loads((run_dir / d["steps"]["packaging"]["outputs"]["metadata"]).read_text(encoding="utf-8"))
    target_langs = normalize_langs(langs) if langs else normalize_langs(d["params"].get("languages"))
    results = []
    for lang in target_langs:
        res = tiktok_upload.upload(lang, run_dir / qa_out[f"video_{lang}"], meta[lang], privacy)
        results.append({"lang": lang, **res})
        store.notify(f"Posted {lang} to TikTok ({res['privacy']}), publish_id {res['publish_id']}", "success")
    (run_dir / "tiktok_uploads.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results
