"""Command line: start a workflow run (with dashboard or headless), resume one, publish, or list what exists."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import webbrowser
from pathlib import Path

import uvicorn
import yaml

from . import ROOT
from .config import load_config
from .engine.registry import Registry
from .engine.state import StateStore
from .runtime import create_run, resume_run
from .server.app import LOCAL_HOSTS, create_app


def parse_param_value(raw: str):
    """Parse CLI `-p key=value` without YAML 1.1 sexagesimal ('9:16' -> 556) or Norway ('no' -> False) traps."""
    val = raw.strip()
    if not val:
        return True
    if (val.startswith("[") and val.endswith("]")) or (val.startswith("{") and val.endswith("}")):
        return yaml.safe_load(val)
    low = val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none", "~"):
        return None
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    if re.fullmatch(r"-?\d+\.\d+", val):
        return float(val)
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val


def parse_params(pairs: list[str]) -> dict:
    params = {}
    for pair in pairs:
        if "=" not in pair:
            params[pair.strip()] = True
            continue
        key, _, value = pair.partition("=")
        params[key.strip()] = parse_param_value(value)
    return params


async def serve(orch, host: str, port: int, open_browser: bool) -> None:
    if host in ("0.0.0.0", "::"):
        print("Warning: dashboard is reachable from other machines (no login). Prefer host 127.0.0.1.")
        allowed = ["*"]
    else:
        allowed = list(dict.fromkeys([*LOCAL_HOSTS, host]))
    server = uvicorn.Server(uvicorn.Config(create_app(orch, allowed), host=host, port=port, log_level="warning"))
    url = f"http://{host}:{port}"
    print(f"Run folder: {orch.store.run_dir}\nDashboard:  {url}\nPress Ctrl+C to stop (the run can be resumed).")
    if open_browser:
        asyncio.get_running_loop().call_later(1.0, webbrowser.open, url)
    server_task = asyncio.create_task(server.serve())
    engine_task = asyncio.create_task(orch.run())
    await asyncio.wait([server_task, engine_task], return_when=asyncio.FIRST_COMPLETED)
    if engine_task.done() and not server_task.done():
        engine_task.result()
        print("Workflow finished. The dashboard stays up until Ctrl+C.")
        await server_task
    else:
        engine_task.cancel()


def run_headless(orch) -> int:
    """For schedulers: run until done, failed, or a checkpoint that needs a human. Exit code 1 on failure."""
    print(f"Run folder: {orch.store.run_dir}", flush=True)
    outcome = asyncio.run(orch.run(headless=True))
    pending = [k for k, v in orch.store.data["checkpoints"].items() if v["status"] == "pending"]
    print(f"Outcome: {outcome}" + (f" (waiting at checkpoint {', '.join(pending)})" if pending else ""))
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"run_dir={orch.store.run_dir.relative_to(ROOT).as_posix()}\nrun_id={orch.store.data['run_id']}\noutcome={outcome}\n")
    return 1 if outcome == "failed" else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="moderator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="start a workflow")
    run_p.add_argument("workflow")
    run_p.add_argument("-p", "--param", action="append", default=[], help="key=value (YAML list/dict or scalar), repeatable")
    run_p.add_argument("--llm", choices=["gemini", "claude"], default=None,
                       help="text model provider for this run (default: config.yaml llm.provider, else gemini); "
                            "claude uses your Claude plan via the Claude Code CLI")
    res_p = sub.add_parser("resume", help="resume a run folder")
    res_p.add_argument("run_dir", type=Path)
    res_p.add_argument("--retry-failed", action="store_true", help="requeue any failed steps before resuming")
    for p in (run_p, res_p):
        p.add_argument("--port", type=int)
        p.add_argument("--no-browser", action="store_true")
        p.add_argument("--headless", action="store_true", help="no dashboard; exit at the first human checkpoint")
    sub.add_parser("list", help="list workflows and agents")
    sum_p = sub.add_parser("summary", help="print the review summary (markdown) of a run")
    sum_p.add_argument("run_dir", type=Path)
    up_p = sub.add_parser("upload", help="approve the final checkpoint of a youtube_short run and upload it")
    up_p.add_argument("run_dir", type=Path)
    up_p.add_argument("--approved-by", required=True, help="who approved the videos (recorded in state.json)")
    up_p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    up_p.add_argument("--langs", help="comma-separated, default: the run's languages")
    tup_p = sub.add_parser("upload-tiktok", help="post an already-approved youtube_short run to TikTok")
    tup_p.add_argument("run_dir", type=Path)
    tup_p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    tup_p.add_argument("--langs", help="comma-separated, default: the run's languages")
    tauth_p = sub.add_parser("tiktok-auth", help="authorize posting to a TikTok account (manual browser flow)")
    tauth_p.add_argument("--redirect-uri", required=True, help="a redirect URI registered in your TikTok app")
    tauth_p.add_argument("--lang", default=None, help="optional language code if using one TikTok account per language")
    edit_p = sub.add_parser("edit", help="apply /edit requests to a run waiting for final approval, then redo it headless")
    edit_p.add_argument("run_dir", type=Path)
    edit_req = edit_p.add_mutually_exclusive_group(required=True)
    edit_req.add_argument("--request", help="one or more '/edit ...' lines (see moderator/edits.py)")
    edit_req.add_argument("--request-file", type=Path, help="read the /edit lines from a file (e.g. an issue comment)")
    edit_p.add_argument("--by", default="you", help="who asked for the edit (recorded in state.json)")
    edit_p.add_argument("--check", action="store_true", help="only parse and print the edits; change nothing")
    auth_p = sub.add_parser("youtube-auth", help="authorize uploads to a YouTube channel (opens the browser)")
    auth_p.add_argument("--lang", default=None, help="optional language code (en/fr/ar) if using separate channels per language")
    auth_p.add_argument("--client-secret", type=Path, required=True, help="OAuth Desktop client JSON from Google Cloud")
    opt_p = sub.add_parser("optimize-channel", help="apply SEO description, keywords, 2560x1440 banner, playlist & video tweaks")
    opt_p.add_argument("--preset", choices=["auto", "psychology", "ai", "hybrid"], default="auto")
    opt_p.add_argument("--country", default="US", help="2-letter target audience country code (default: US)")
    opt_p.add_argument("--lang", default="en", help="channel default language (default: en)")
    opt_p.add_argument("--client-secret", type=Path, default=ROOT / "client_secret.json")
    opt_p.add_argument("--reauth", action="store_true", help="force fresh OAuth consent with channel-management scope")
    opt_p.add_argument("--dry-run", action="store_true", help="render the banner and print the planned changes without writing to YouTube")
    pages_p = sub.add_parser("export-pages", help="export static dashboard & run snapshots for GitHub Pages")
    pages_p.add_argument("site_dir", type=Path, help="output folder (e.g. a gh-pages worktree)")
    pages_p.add_argument("--repo", default=None, help="GitHub owner/repo slug")
    pages_p.add_argument("--runs-dir", type=Path, default=None, help="runs folder to read from (default: ./runs)")
    pages_p.add_argument("--run-id", default=None, help="target run_id for --issue-url / --gh-run-url")
    pages_p.add_argument("--issue-url", default=None, help="GitHub review issue URL")
    pages_p.add_argument("--gh-run-url", default=None, help="GitHub Actions run URL")
    pages_p.add_argument("--max-runs", type=int, default=10, help="maximum historical runs to retain on Pages")
    pages_p.add_argument("--no-media", action="store_true", help="skip mp4/mp3 files (fast mid-run progress sync)")
    sub.add_parser("cache-stats", help="inspect LLM response cache hit rates and USD savings")
    cc_p = sub.add_parser("cache-clear", help="purge cached LLM responses to free disk space")
    cc_p.add_argument("--expired-only", action="store_true", help="only delete expired cache entries")
    args = parser.parse_args()

    config = load_config(ROOT)

    if args.cmd == "cache-stats":
        from .engine.llm_cache import default_cache
        stats = default_cache.get_stats()
        print("LLM Response Cache Statistics:")
        print(f"  Status:         {'Enabled' if stats.get('enabled') else 'Disabled'}")
        print(f"  Database Path:  {stats.get('db_path')}")
        print(f"  Total Entries:  {stats.get('total_entries', 0)}")
        print(f"  Active Entries: {stats.get('active_entries', 0)}")
        print(f"  Cache Hits:     {stats.get('total_hits', 0)}")
        print(f"  Tokens Saved:   {stats.get('tokens_saved', 0):,}")
        print(f"  Cost Saved:     ${stats.get('usd_saved', 0.0):.4f}")
        return

    if args.cmd == "cache-clear":
        from .engine.llm_cache import default_cache
        deleted = default_cache.clear(expired_only=args.expired_only)
        scope = "expired" if args.expired_only else "all"
        print(f"Cleared {deleted} {scope} cache entries from LLM cache.")
        return

    if args.cmd == "export-pages":
        from .pages import export_pages
        manifest = export_pages(
            args.site_dir,
            repo=args.repo,
            runs_dir=args.runs_dir,
            target_run_id=args.run_id,
            issue_url=args.issue_url,
            gh_run_url=args.gh_run_url,
            max_runs=args.max_runs,
            include_media=not args.no_media,
        )
        print(f"Exported GitHub Pages site to {args.site_dir} ({len(manifest['runs'])} run(s)).")
        return

    if args.cmd == "youtube-auth":
        from .tools import youtube_upload
        path, channel = youtube_upload.authorize(args.client_secret, args.lang, scopes=youtube_upload.UPLOAD_SCOPES)
        secret_name = f"YOUTUBE_TOKEN_{args.lang.upper()}" if args.lang else "YOUTUBE_TOKEN"
        target_label = f"language '{args.lang}'" if args.lang else "all languages (default channel)"
        print(f"Authorized channel '{channel}' for {target_label}. Token saved to {path}")
        print(f"Scopes: upload + read-only (cannot edit or delete videos). For GitHub Actions, store the whole file "
              f"content as the repository secret {secret_name}.")
        return
    if args.cmd == "tiktok-auth":
        from .tools import tiktok_upload
        path = tiktok_upload.authorize(args.redirect_uri, args.lang)
        secret_name = f"TIKTOK_TOKEN_{args.lang.upper()}" if args.lang else "TIKTOK_TOKEN"
        print(f"Token saved to {path}. For GitHub Actions store the whole file content as the repository secret "
              f"{secret_name}, plus TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET.")
        return
    if args.cmd == "upload-tiktok":
        from .publish import upload_tiktok
        for r in upload_tiktok(StateStore.load(args.run_dir), args.privacy,
                               args.langs.split(",") if args.langs else None):
            print(f"{r['lang']}: TikTok {r['status']} ({r['privacy']}), publish_id {r['publish_id']}")
        return
    if args.cmd == "optimize-channel":
        from .tools import youtube_channel
        res = youtube_channel.optimize_channel(
            lang=args.lang,
            preset=args.preset,
            country=args.country,
            client_secret=args.client_secret,
            reauth=args.reauth,
            dry_run=args.dry_run,
        )
        sys.stdout.reconfigure(encoding="utf-8")
        if res["dry_run"]:
            print(f"DRY RUN for '{res['current_title']}' ({res['channel_url']}) [{res['mode']}]: nothing was changed")
            print(f"  Country / Lang: {res['country']} / {res['default_language']}")
            print(f"  Banner preview: {res['banner_path']}")
            print("  Description:\n    " + res["description"].replace("\n", "\n    "))
            print(f"  Keywords: {res['keywords']}")
            print(f"  Video changes ({len(res['video_changes'])}):")
            for vid, ch in res["video_changes"].items():
                print(f"    {vid}: {ch['from']!r} -> {ch['title']!r}")
                print(f"      description starts: {ch['description'].splitlines()[0]!r}")
        else:
            print(f"Optimized channel '{res['current_title']}' ({res['channel_url']}) [{res['mode']}]")
            print(f"  Country / Lang: {res['country']} / {res['default_language']}")
            print(f"  Banner uploaded: {res['banner_path']}")
            print(f"  Shorts playlist: {res['playlist_url']}")
            print(f"  Optimized videos: {len(res['updated_videos'])} ({', '.join(res['updated_videos']) or 'none needed'})")
        print(f"  Tip: {res['studio_tip']}")
        return
    if args.cmd == "summary":
        from .publish import review_summary
        sys.stdout.reconfigure(encoding="utf-8")
        print(review_summary(StateStore.load(args.run_dir)))
        return
    if args.cmd == "upload":
        from .publish import approve_and_upload
        results = approve_and_upload(StateStore.load(args.run_dir), args.approved_by, args.privacy,
                                     args.langs.split(",") if args.langs else None)
        sys.stdout.reconfigure(encoding="utf-8")
        for r in results:
            print(f"{r['lang']}: {r['url']} ({r['privacy']}) on '{r['channel']}'" + (f", thumbnail {r['thumbnail']}" if r.get("thumbnail") else ""))
        return

    registry = Registry(ROOT, config)
    if args.cmd == "list":
        print("Workflows:")
        for name in registry.workflows():
            wf = registry.workflow(name)
            print(f"  {name:20} {wf.title}")
        print("Agents:")
        for spec in registry.specs.values():
            print(f"  {spec.name:20} {spec.title}")
        return

    if args.cmd == "edit":
        from .edits import EditError, apply_edits, parse_edits
        sys.stdout.reconfigure(encoding="utf-8")
        request = args.request if args.request is not None else args.request_file.read_text(encoding="utf-8")
        orch = resume_run(registry, args.run_dir)
        script_path = orch.store.run_dir / "script.json"
        n_scenes = len(json.loads(script_path.read_text(encoding="utf-8"))["scenes"]) if script_path.exists() else 0
        try:
            edits = parse_edits(request, n_scenes)
            if not args.check:
                apply_edits(orch, edits, by=args.by)
        except EditError as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)
        print("Edits:\n" + "\n".join(f"- {e.describe()}" for e in edits))
        if args.check:
            return
        sys.exit(run_headless(orch))

    if args.cmd == "run":
        params = parse_params(args.param)
        if args.llm:
            params["llm"] = args.llm  # stored with the run, so `resume` keeps the same provider
        orch = create_run(registry, args.workflow, params)
    else:
        orch = resume_run(registry, args.run_dir)
    if args.cmd == "resume" and args.retry_failed:
        orch.retry_failed()
    if args.headless:
        sys.exit(run_headless(orch))
    srv = config.get("server", {})
    try:
        asyncio.run(serve(orch, srv.get("host", "127.0.0.1"), args.port or srv.get("port", 8765), not args.no_browser))
    except KeyboardInterrupt:
        print(f"\nStopped. Resume with: python -m moderator resume {orch.store.run_dir}")
