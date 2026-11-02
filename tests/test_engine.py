import asyncio
import json
from pathlib import Path

import pytest

from moderator import ROOT
from moderator.engine.orchestrator import Orchestrator
from moderator.engine.registry import Registry
from moderator.engine.state import StateStore, new_state
from moderator.engine.workflow import WorkflowError, load_workflow


def make_orch(tmp_path: Path, **step_overrides) -> Orchestrator:
    registry = Registry(ROOT, {})
    wf = registry.workflow("demo")
    for step in wf.steps:
        step.options = {**step.options, "seconds": 0.05, **step_overrides.get(step.id, {})}
    agents = {s.agent: registry.specs[s.agent].public() for s in wf.steps}
    store = StateStore.create(tmp_path / "run", new_state("test", wf, {}, agents))
    return Orchestrator(store, wf, registry)


async def drive(orch: Orchestrator, decide, timeout: float = 20) -> None:
    """Run the workflow, answering each pending checkpoint with decide(cp_id, cp) -> kwargs."""
    async def approver():
        while True:
            for cp_id, cp in list(orch.store.data["checkpoints"].items()):
                if cp["status"] == "pending":
                    orch.decide(cp_id, **decide(cp_id, cp))
            await asyncio.sleep(0.02)

    helper = asyncio.create_task(approver())
    try:
        await asyncio.wait_for(orch.run(), timeout)
    finally:
        helper.cancel()


def approve_all(cp_id, cp):
    return {"action": "approve", "choice": "opt2" if cp["type"] == "choice" else None}


def test_full_run_with_retry_and_reviewer_revision(tmp_path):
    orch = make_orch(tmp_path)
    asyncio.run(drive(orch, approve_all))
    d = json.loads((tmp_path / "run" / "state.json").read_text(encoding="utf-8"))

    assert d["status"] == "done"
    assert all(s["status"] == "done" for s in d["steps"].values())
    assert d["checkpoints"]["A"]["choice"] == "opt2"
    # images failed once, then the retry used the next strategy
    assert d["steps"]["images"]["errors"][0]["strategy"] == "default"
    # the reviewer sent images back once, which also re-ran everything downstream of it
    assert d["revision_rounds"] == 1
    assert d["steps"]["images"]["feedback"][0]["from"] == "review"
    assert d["steps"]["review"]["attempt"] == 2
    assert d["cost"]["total_usd"] > 0


def test_request_changes_routes_to_configured_step(tmp_path):
    orch = make_orch(tmp_path)
    asked = []

    def decide(cp_id, cp):
        if cp_id == "C" and not asked:
            asked.append(cp_id)
            return {"action": "request_changes", "comment": "Tighten the ending"}
        return approve_all(cp_id, cp)

    asyncio.run(drive(orch, decide))
    d = orch.store.data
    assert d["status"] == "done"
    last = d["steps"]["assemble"]["feedback"][-1]
    assert (last["from"], last["comment"]) == ("you", "Tighten the ending")
    assert d["checkpoints"]["C"]["status"] == "approved"
    assert d["steps"]["review"]["attempt"] == 3  # reviewer revision, then the human's request


def test_step_fails_after_retries_and_blocks_downstream(tmp_path):
    orch = make_orch(tmp_path, audio={"always_fail": True})

    async def scenario():
        task = asyncio.create_task(orch.run())
        for _ in range(500):
            for cp_id, cp in orch.store.data["checkpoints"].items():
                if cp["status"] == "pending":
                    orch.decide(cp_id, **approve_all(cp_id, cp))
            if orch.store.data["status"] == "failed":
                break
            await asyncio.sleep(0.02)
        task.cancel()

    asyncio.run(scenario())
    d = orch.store.data
    assert d["status"] == "failed"
    assert d["steps"]["audio"]["status"] == "failed"
    assert len(d["steps"]["audio"]["errors"]) == 3
    assert d["steps"]["assemble"]["status"] == "queued"
    assert any(n["level"] == "error" for n in d["notifications"])


def test_choice_checkpoint_requires_a_valid_option(tmp_path):
    orch = make_orch(tmp_path)

    async def scenario():
        task = asyncio.create_task(orch.run())
        while orch.store.data["checkpoints"]["A"]["status"] != "pending":
            await asyncio.sleep(0.02)
        with pytest.raises(ValueError):
            orch.decide("A", "approve", choice="nope")
        task.cancel()

    asyncio.run(scenario())


def test_headless_auto_approves_and_stops_at_human_checkpoint(tmp_path):
    orch = make_orch(tmp_path)
    orch.store.data["params"]["auto_approve"] = ["A", "B"]
    outcome = asyncio.run(asyncio.wait_for(orch.run(headless=True), 20))
    d = orch.store.data
    assert outcome == "waiting"
    assert d["checkpoints"]["A"]["choice"] == "opt1"  # top-ranked option
    assert d["checkpoints"]["B"]["status"] == "approved"
    assert d["checkpoints"]["C"]["status"] == "pending"
    assert any("schedule" in l["msg"] for l in d["steps"]["ideas"]["logs"])


def test_headless_returns_failed(tmp_path):
    orch = make_orch(tmp_path, ideas={"always_fail": True})
    assert asyncio.run(asyncio.wait_for(orch.run(headless=True), 20)) == "failed"


def test_cycle_is_rejected(tmp_path):
    wf = tmp_path / "bad.yaml"
    wf.write_text("steps:\n  - {id: a, agent: x, depends_on: [b]}\n  - {id: b, agent: x, depends_on: [a]}\n")
    with pytest.raises(WorkflowError):
        load_workflow(wf)
