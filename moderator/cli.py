"""Command line: start a workflow run (with dashboard or headless), resume one, publish, or list what exists."""

from __future__ import annotations

import argparse
import asyncio
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
from .server.app import create_app


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
    server = uvicorn.Server(uvicorn.Config(create_app(orch), host=host, port=port, log_level="warning"))
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
    auth_p = sub.add_parser("youtube-auth", help="authorize uploads to a YouTube channel (opens the browser)")
    auth_p.add_argument("--lang", default=None, help="optional language code (en/fr/ar) if using separate channels per language")
    auth_p.add_argument("--client-secret", type=Path, required=True, help="OAuth Desktop client JSON from Google Cloud")
    args = parser.parse_args()

    config = load_config(ROOT)

    if args.cmd == "youtube-auth":
        from .tools import youtube_upload
        path, channel = youtube_upload.authorize(args.client_secret, args.lang)
        secret_name = f"YOUTUBE_TOKEN_{args.lang.upper()}" if args.lang else "YOUTUBE_TOKEN"
        target_label = f"language '{args.lang}'" if args.lang else "all languages (default channel)"
        print(f"Authorized channel '{channel}' for {target_label}. Token saved to {path}")
        print(f"For GitHub Actions, store the whole file content as the repository secret {secret_name}.")
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

    orch = (create_run(registry, args.workflow, parse_params(args.param)) if args.cmd == "run"
            else resume_run(registry, args.run_dir))
    if args.cmd == "resume" and args.retry_failed:
        orch.retry_failed()
    if args.headless:
        sys.exit(run_headless(orch))
    srv = config.get("server", {})
    try:
        asyncio.run(serve(orch, srv.get("host", "127.0.0.1"), args.port or srv.get("port", 8765), not args.no_browser))
    except KeyboardInterrupt:
        print(f"\nStopped. Resume with: python -m moderator resume {orch.store.run_dir}")
