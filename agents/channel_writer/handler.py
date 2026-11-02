from pathlib import Path

import yaml

from moderator.engine.agent import Agent, StepContext


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        cp = ctx.options.get("checkpoint", "N")
        choice = ctx.decision(cp)["choice"]
        niche = next(n for n in ctx.read_json("niches.json")["niches"] if n["id"] == choice)
        ctx.set_inputs(niche=niche["name"])
        channel = {
            "niche": niche["name"],
            "niche_summary": niche["summary"],
            "example_topics": niche["example_topics"],
            "languages": ctx.params.get("languages", ["ar", "fr"]),
            "style": ctx.params.get("style"),
        }
        text = yaml.safe_dump(channel, allow_unicode=True, sort_keys=False)
        Path(self.config["root"], "channel.yaml").write_text(text, encoding="utf-8")
        ctx.path("channel.yaml").write_text(text, encoding="utf-8")
        ctx.log(f"Saved channel niche: {niche['name']}")
        return {"channel": "channel.yaml"}
