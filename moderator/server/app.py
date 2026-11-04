"""Dashboard server: serves the page, the run state, the run's media files, historical runs, and approval actions."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..engine.orchestrator import Orchestrator

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
LOCAL_HOSTS = ["127.0.0.1", "localhost", "::1", "[::1]"]
WRITE_HEADER = "x-moderator"


class Decision(BaseModel):
    action: str  # "approve" | "request_changes"
    comment: str | None = None
    choice: str | None = None
    route_to: str | None = None


def create_app(orch: Orchestrator, allowed_hosts: list[str] | None = None) -> FastAPI:
    app = FastAPI(title="moderator")
    # Host check blocks DNS-rebinding pages from reading or driving the dashboard
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or LOCAL_HOSTS)

    @app.middleware("http")
    async def require_dashboard_header(request: Request, call_next):
        """State-changing calls must carry a custom header. Browsers cannot add one to a cross-site form, and a
        cross-site fetch with it needs a CORS preflight this server never grants, so other websites cannot
        press the dashboard's buttons."""
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(WRITE_HEADER) != "1":
            return JSONResponse({"detail": f"missing {WRITE_HEADER} header"}, status_code=403)
        return await call_next(request)
    store = orch.store
    run_dir = store.run_dir.resolve()
    runs_root = run_dir.parent.resolve()

    def _resolve_run_dir(run_id: str) -> Path:
        if run_id == store.data["run_id"]:
            return run_dir
        if not SAFE_RUN_ID.fullmatch(run_id):
            raise HTTPException(404, "unknown run")
        cand = (runs_root / run_id).resolve()
        if not cand.is_relative_to(runs_root) or not (cand / "state.json").is_file():
            raise HTTPException(404, "unknown run")
        return cand

    @app.get("/")
    def index():
        return FileResponse(DASHBOARD / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    @app.get("/state.json")
    async def state():
        return JSONResponse(store.snapshot(), headers={"Cache-Control": "no-store"})

    @app.get("/api/runs")
    async def list_runs():
        live_id = store.data["run_id"]
        items = []
        candidates = sorted(runs_root.glob("*/state.json"), reverse=True) if runs_root.is_dir() else []
        seen = set()
        for sf in candidates[:40]:
            rid = sf.parent.name
            seen.add(rid)
            if rid == live_id:
                snap = store.snapshot()
            else:
                try:
                    snap = json.loads(sf.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
            items.append({
                "run_id": snap.get("run_id", rid),
                "workflow": snap.get("workflow", ""),
                "workflow_title": snap.get("workflow_title", rid),
                "status": snap.get("status", "unknown"),
                "started_at": snap.get("started_at"),
                "is_live": rid == live_id,
            })
        if live_id not in seen:
            snap = store.snapshot()
            items.insert(0, {
                "run_id": live_id,
                "workflow": snap.get("workflow", ""),
                "workflow_title": snap.get("workflow_title", live_id),
                "status": snap.get("status", "running"),
                "started_at": snap.get("started_at"),
                "is_live": True,
            })
        return JSONResponse({"live_run_id": live_id, "runs": items}, headers={"Cache-Control": "no-store"})

    @app.get("/api/runs/{run_id}/state")
    async def run_state(run_id: str):
        if run_id == store.data["run_id"]:
            return JSONResponse(store.snapshot(), headers={"Cache-Control": "no-store"})
        target_dir = _resolve_run_dir(run_id)
        data = json.loads((target_dir / "state.json").read_text(encoding="utf-8"))
        return JSONResponse(data, headers={"Cache-Control": "no-store"})

    @app.get("/api/runs/{run_id}/files/{rel:path}")
    def run_files(run_id: str, rel: str):
        target_dir = _resolve_run_dir(run_id)
        path = (target_dir / rel).resolve()
        if not path.is_relative_to(target_dir) or not path.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    @app.post("/api/checkpoints/{cp_id}")
    async def decide(cp_id: str, body: Decision):  # async: runs on the engine loop, so wake.set() is safe
        try:
            orch.decide(cp_id, body.action, comment=(body.comment or "").strip() or None,
                        choice=body.choice, route_to=body.route_to)
        except KeyError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    @app.post("/api/steps/{step_id}/retry")
    async def retry(step_id: str):
        if step_id not in store.data["steps"]:
            raise HTTPException(404, "unknown step")
        try:
            orch.retry(step_id)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    @app.post("/api/retry-failed")
    async def retry_all():
        retried = orch.retry_failed()
        if not retried:
            raise HTTPException(409, "no failed steps to retry")
        return {"ok": True, "retried": retried}

    @app.get("/files/{rel:path}")
    def files(rel: str):
        path = (run_dir / rel).resolve()
        if not path.is_relative_to(run_dir) or not path.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=DASHBOARD), name="static")
    return app
