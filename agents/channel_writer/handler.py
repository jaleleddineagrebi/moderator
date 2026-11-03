from pathlib import Path

import yaml

from moderator.engine.agent import Agent, StepContext
from moderator.tools.languages import normalize_langs


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        cp = ctx.options.get("checkpoint", "N")
        choice = ctx.decision(cp)["choice"]
        scout_data = ctx.upstream("scout").get("data", "niches.json")
        niche = next(n for n in ctx.read_json(scout_data)["niches"] if n["id"] == choice)
        langs = normalize_langs(ctx.params.get("languages"))
        ctx.set_inputs(niche=niche["name"], languages=langs)
        channel = {
            "niche": niche["name"],
            "niche_summary": niche["summary"],
            "example_topics": niche["example_topics"],
            "languages": langs,
            "style": ctx.params.get("style"),
        }
        text = yaml.safe_dump(channel, allow_unicode=True, sort_keys=False)
        Path(self.config["root"], "channel.yaml").write_text(text, encoding="utf-8")
        ctx.path("channel.yaml").write_text(text, encoding="utf-8")
        ctx.log(f"Saved channel niche: {niche['name']}")
        return {"channel": "channel.yaml"}
