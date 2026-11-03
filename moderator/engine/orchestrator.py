"""Runs a workflow: schedules steps as their dependencies finish, retries failures with
the next strategy, pauses at checkpoints, and routes revision feedback upstream."""

from __future__ import annotations

import asyncio
import traceback

from .agent import BudgetExceeded, StepContext
from .registry import Registry
from .state import StateStore, now_iso
from .workflow import Workflow


class Orchestrator:
    def __init__(self, store: StateStore, workflow: Workflow, registry: Registry):
        self.store = store
        self.workflow = workflow
        self.registry = registry
        self.wake = asyncio.Event()
        self.tasks: dict[str, asyncio.Task] = {}
        self._cancelled_for_reset: set[str] = set()

    @property
    def steps(self) -> dict:
        return self.store.data["steps"]

    async def run(self, headless: bool = False) -> str:
        """Returns "done" when every step is done. With the dashboard, a failed workflow keeps waiting
        for a manual retry. Headless (scheduled) runs instead return "failed", or "waiting" when the
        only thing left is a checkpoint that needs a human."""
        self._recover()
        while True:
            self.wake.clear()
            self._schedule()
            outcome = self._outcome()
            if outcome and self.store.data["status"] != outcome:
                with self.store.mutate() as d:
                    d["status"] = outcome
                    d["ended_at"] = now_iso()
                if outcome == "done":
                    self.store.notify("Workflow finished. Nothing was published.", "success")
            if outcome == "done":
                return "done"
            if headless and outcome == "failed":
                return "failed"
            if headless and not self.tasks:
                return "waiting"
            await self.wake.wait()

    def _recover(self) -> None:
        """A step marked running when the process starts was interrupted; run it again."""
        with self.store.mutate() as d:
            if d["status"] != "done":
                d["status"] = "running"
                d["ended_at"] = None
            for s in d["steps"].values():
                if s["status"] == "running":
                    s["status"] = "queued"
                    s["progress"] = 0

    def _schedule(self) -> None:
        for step in self.workflow.steps:
            st = self.steps[step.id]
            if step.id in self.tasks or st["status"] not in ("queued", "needs_revision"):
                continue
            if all(self.steps[d]["status"] == "done" for d in step.depends_on):
                self.tasks[step.id] = asyncio.create_task(self._run_step(step.id))

    def _outcome(self) -> str | None:
        statuses = [s["status"] for s in self.steps.values()]
        if all(s == "done" for s in statuses):
            return "done"
        if self.tasks or "waiting_for_approval" in statuses:
            return None
        return "failed" if "failed" in statuses else None

    async def _run_step(self, step_id: str) -> None:
        step = self.workflow.step_map[step_id]
        agent = self.registry.agent(step.agent)
        strategies = agent.spec.strategies or ["default"]
        max_retries = self.workflow.settings["max_retries"]
        backoff_s = float(self.workflow.settings.get("retry_backoff_s") or 0.0)
        try:
            for retry in range(max_retries + 1):
                if retry > 0 and backoff_s > 0:
                    await asyncio.sleep(backoff_s * (2 ** (retry - 1)))
                strategy = strategies[min(retry, len(strategies) - 1)]
                with self.store.mutate() as d:
                    st = d["steps"][step_id]
                    st.update(status="running", progress=0, retries=retry, strategy=strategy,
                              started_at=now_iso(), ended_at=None)
                    st["attempt"] += 1
                self.store.log(step_id, f"Attempt {retry + 1}/{max_retries + 1}, strategy '{strategy}'")
                ctx = StepContext(store=self.store, step_id=step_id, attempt=retry + 1, strategy=strategy,
                                  options=step.options, config=self.registry.config)
                try:
                    outputs = await asyncio.wait_for(agent.run(ctx), agent.spec.timeout_s)
                except asyncio.CancelledError:
                    if step_id in self._cancelled_for_reset:
                        self._cancelled_for_reset.discard(step_id)
                        return
                    raise
                except Exception as e:  # noqa: BLE001 - any agent failure is retried
                    msg = f"{type(e).__name__}: {e}"
                    with self.store.mutate() as d:
                        d["steps"][step_id]["errors"].append({
                            "ts": now_iso(), "attempt": retry + 1, "strategy": strategy, "error": msg,
                            "trace": traceback.format_exc(limit=6)[-2000:],
                        })
                    self.store.log(step_id, msg, "error")
                    if isinstance(e, BudgetExceeded):
                        break
                    continue
                self._finish(step_id, outputs or {}, ctx)
                return
            with self.store.mutate() as d:
                d["steps"][step_id].update(status="failed", ended_at=now_iso())
            self.store.notify(f"'{step.title}' failed after {max_retries + 1} attempts. "
                              "Open it on the dashboard and press Retry once fixed.", "error", step_id)
        finally:
            self._cancelled_for_reset.discard(step_id)
            self.tasks.pop(step_id, None)
            self.wake.set()

    def _finish(self, step_id: str, outputs: dict, ctx: StepContext) -> None:
        step = self.workflow.step_map[step_id]
        with self.store.mutate() as d:
            st = d["steps"][step_id]
            st.update(outputs=outputs, progress=100, ended_at=now_iso())
            if step.checkpoint:
                st["status"] = "waiting_for_approval"
                d["checkpoints"][step.checkpoint.id].update(status="pending", choice=None, comment=None, decided_at=None)
            else:
                st["status"] = "done"
        self.store.log(step_id, "Finished" + (", waiting for your approval" if step.checkpoint else ""))
        if ctx.revision_requests:
            self._apply_revisions(step_id, ctx.revision_requests)
        if step.checkpoint and self.store.data["steps"][step_id]["status"] == "waiting_for_approval":
            if step.checkpoint.id in (self.store.data["params"].get("auto_approve") or []):
                self._auto_approve(step.checkpoint.id)
            else:
                self.store.notify(f"Approval needed: {step.checkpoint.title}", "action", step_id)

    def _auto_approve(self, cp_id: str) -> None:
        """Scheduled runs approve some checkpoints themselves; a choice takes the top-ranked option."""
        cp = self.store.data["checkpoints"][cp_id]
        choice = cp["options"][0]["id"] if cp["type"] == "choice" and cp["options"] else None
        if cp["type"] == "choice" and not choice:
            self.store.notify(f"Approval needed: {cp['title']} (no options to pick automatically)", "action", cp["step"])
            return
        self.decide(cp_id, "approve", choice=choice, by="schedule (auto-approve)")

    def _apply_revisions(self, reviewer: str, requests: list[tuple[str, str]]) -> None:
        limit = self.workflow.settings["max_revision_rounds"]
        if self.store.data["revision_rounds"] >= limit:
            self.store.log(reviewer, f"Revision limit ({limit} rounds) reached; passing the issues to you instead", "warning")
            self.store.notify(f"Reviewer still had issues after {limit} revision rounds. Check its report.", "warning", reviewer)
            return
        with self.store.mutate() as d:
            d["revision_rounds"] += 1
        all_targets = {t for t, _ in requests}
        for target, feedback in requests:
            self.send_back(target, feedback, source=reviewer, preserve_revising=all_targets)

    def send_back(self, target: str, feedback: str, source: str, *, preserve_revising: set[str] | None = None) -> None:
        """Mark target as needs_revision with feedback, cancel in-flight downstream tasks, and requeue downstream."""
        if target not in self.steps:
            raise KeyError(f"unknown step '{target}'")
        reset = self.workflow.downstream(target)
        keep_rev = preserve_revising or set()
        for sid in [target, *reset]:
            task = self.tasks.get(sid)
            if task and not task.done() and task is not asyncio.current_task():
                self._cancelled_for_reset.add(sid)
                task.cancel()
        with self.store.mutate() as d:
            t = d["steps"][target]
            t.update(status="needs_revision", progress=0, retries=0)
            t["feedback"].append({"ts": now_iso(), "from": source, "comment": feedback})
            for sid in reset:
                s = d["steps"][sid]
                next_status = "needs_revision" if (sid in keep_rev and s["status"] == "needs_revision") else "queued"
                s.update(status=next_status, progress=0, retries=0)
                s["logs"].append({"ts": now_iso(), "level": "info", "msg": f"Reset: upstream step '{target}' is being revised"})
            for cp in d["checkpoints"].values():
                keep_request = cp["step"] == target and cp["status"] == "changes_requested"
                if (cp["step"] in reset or cp["step"] == target) and not keep_request:
                    cp["status"] = "idle"
            if d["status"] != "running":
                d["status"] = "running"
                d["ended_at"] = None
        self.store.log(target, f"Sent back by {source}: {feedback}", "warning")
        self.wake.set()

    # Called from the dashboard

    def decide(self, cp_id: str, action: str, comment: str | None = None, choice: str | None = None,
               route_to: str | None = None, by: str = "you") -> None:
        cps = self.store.data["checkpoints"]
        if cp_id not in cps:
            raise KeyError(f"unknown checkpoint '{cp_id}'")
        cp = cps[cp_id]
        if cp["status"] != "pending":
            raise ValueError(f"checkpoint {cp_id} is not waiting for a decision")
        if action == "approve":
            if cp["type"] == "choice" and choice not in {o["id"] for o in cp["options"]}:
                raise ValueError("pick one of the options before approving")
            with self.store.mutate() as d:
                d["checkpoints"][cp_id].update(status="approved", choice=choice, comment=comment, decided_at=now_iso())
                d["steps"][cp["step"]]["status"] = "done"
            self.store.log(cp["step"], f"Approved by {by}" + (f" (choice: {choice})" if choice else ""))
        elif action == "request_changes":
            if not comment:
                raise ValueError("describe the changes you want")
            target = route_to or cp["route_to"]
            if target != cp["step"] and cp["step"] not in self.workflow.downstream(target):
                raise ValueError(f"'{target}' is not upstream of this checkpoint")
            with self.store.mutate() as d:
                d["checkpoints"][cp_id].update(status="changes_requested", choice=choice, comment=comment, decided_at=now_iso())
            self.send_back(target, comment, source="you")
        else:
            raise ValueError(f"unknown action '{action}'")
        self.wake.set()

    def retry(self, step_id: str) -> None:
        if self.steps[step_id]["status"] != "failed":
            raise ValueError("only failed steps can be retried")
        with self.store.mutate() as d:
            d["steps"][step_id].update(status="queued", retries=0, progress=0)
            d["status"] = "running"
            d["ended_at"] = None
        self.store.log(step_id, "Manual retry requested")
        self.wake.set()

    def retry_failed(self) -> list[str]:
        """Requeue every currently failed step."""
        failed = [sid for sid, st in self.steps.items() if st["status"] == "failed"]
        if not failed:
            return []
        with self.store.mutate() as d:
            for sid in failed:
                d["steps"][sid].update(status="queued", retries=0, progress=0)
            d["status"] = "running"
            d["ended_at"] = None
        for sid in failed:
            self.store.log(sid, "Manual retry requested")
        self.wake.set()
        return failed
