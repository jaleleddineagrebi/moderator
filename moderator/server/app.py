"""Dashboard server: serves the page, the run state, the run's media files, and approval actions."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..engine.orchestrator import Orchestrator

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"


class Decision(BaseModel):
    action: str  # "approve" | "request_changes"
    comment: str | None = None
    choice: str | None = None
    route_to: str | None = None


def create_app(orch: Orchestrator) -> FastAPI:
    app = FastAPI(title="moderator")
    store = orch.store
    run_dir = store.run_dir.resolve()

    @app.get("/")
    def index():
        return FileResponse(DASHBOARD / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    @app.get("/state.json")
    async def state():
        return JSONResponse(store.snapshot(), headers={"Cache-Control": "no-store"})

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

    @app.get("/files/{rel:path}")
    def files(rel: str):
        path = (run_dir / rel).resolve()
        if not path.is_relative_to(run_dir) or not path.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=DASHBOARD), name="static")
    return app
