"""Fake agent. Step options (the `with:` block in the workflow):
seconds     how long to "work"
choices     number of options to offer at a choice checkpoint
fail_first  raise on the first attempt, to exercise retries
always_fail raise on every attempt, to exercise the failed state
revise_once send this step back once (as a reviewer would), to exercise revision routing
"""

import asyncio

from moderator.engine.agent import Agent, StepContext


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        opts = ctx.options
        ticks = 5
        ctx.set_inputs(**{dep: ctx.upstream(dep) for dep in ctx.store.data["steps"][ctx.step_id]["depends_on"]})
        if ctx.feedback:
            ctx.log(f"Revising with feedback: {ctx.feedback[-1]['comment']}")
        for i in range(ticks):
            await asyncio.sleep(opts.get("seconds", 3) / ticks)
            ctx.progress((i + 1) * 100 / ticks)
            ctx.log(f"Working ({i + 1}/{ticks})")
            if (opts.get("fail_first") and ctx.attempt == 1 or opts.get("always_fail")) and i == 2:
                raise RuntimeError(f"simulated failure on attempt {ctx.attempt}")
        if opts.get("choices"):
            ctx.offer_choices([{"id": f"opt{n}", "label": f"Option {n}", "detail": f"Demo option number {n}"}
                               for n in range(1, opts["choices"] + 1)])
        target = opts.get("revise_once")
        if target and ctx.revision_round == 0:
            ctx.request_revision(target, "Demo reviewer: please redo this once")
        ctx.add_cost(0.01)
        out = ctx.write_json(f"demo_{ctx.step_id}.json", {"step": ctx.step_id, "attempt": ctx.attempt,
                                                           "strategy": ctx.strategy})
        return {"result": out}
