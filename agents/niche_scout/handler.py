import json

from moderator.engine.agent import Agent, StepContext
from moderator.tools import youtube
from moderator.tools.languages import LANGS

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["niches"],
    "properties": {"niches": {"type": "array", "minItems": 5, "maxItems": 5, "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "name", "summary", "scores", "total", "best_language", "example_topics", "risks", "evidence"],
        "properties": {
            "id": {"type": "string", "description": "short slug"},
            "name": {"type": "string"},
            "summary": {"type": "string", "description": "why this niche, 2-3 sentences"},
            "scores": {"type": "object", "additionalProperties": False,
                       "required": ["demand", "competition", "monetization", "faceless_fit", "copyright_safety"],
                       "properties": {k: {"type": "integer", "minimum": 1, "maximum": 10} for k in
                                      ("demand", "competition", "monetization", "faceless_fit", "copyright_safety")}},
            "total": {"type": "number"},
            "best_language": {"type": "string", "enum": ["ar", "fr", "both"]},
            "example_topics": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
            "risks": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}, "description": "sources and data points (URLs, view counts)"},
        },
    }}},
}

SEEDS = ["science facts", "history facts", "psychology facts", "space", "animals facts", "personal finance tips",
         "productivity", "technology explained", "geography facts", "health myths"]


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        langs = ctx.params.get("languages", ["ar", "fr"])
        focus = ctx.params.get("focus", "")
        ctx.set_inputs(languages=langs, style=ctx.params.get("style"), focus=focus or None)

        evidence = ""
        if ctx.strategy == "web_and_youtube" and youtube.available():
            ctx.log("Collecting YouTube view data for seed niches")
            rows = {}
            seeds = SEEDS[:6]
            for i, seed in enumerate(seeds):
                for lang in langs:
                    try:
                        vids = await youtube.top_recent_shorts(seed, lang, days=30, limit=5)
                    except Exception as e:  # noqa: BLE001 - evidence is optional
                        ctx.log(f"YouTube lookup failed for '{seed}' ({lang}): {e}", "warning")
                        continue
                    rows[f"{seed} [{lang}]"] = [{"views": v["views"], "title": v["title"], "channel": v["channel"]} for v in vids]
                ctx.progress(5 + 35 * (i + 1) / len(seeds))
            evidence = "YOUTUBE DATA (top Shorts of the last 30 days per seed query):\n" + json.dumps(rows, ensure_ascii=False)[:20000]
        elif ctx.strategy == "web_and_youtube":
            ctx.log("No YOUTUBE_API_KEY set; relying on web research only", "warning")

        breadth = "Consider at least 12 candidate niches before choosing 5." if ctx.strategy != "web_only_fewer_candidates" \
            else "Keep research short: consider about 8 candidates."
        prompt = f"""You are a YouTube Shorts market researcher. Find the 5 best niches for a NEW faceless Shorts channel.

Audience languages: {'; '.join(l + ' = ' + LANGS[l]['name'] + ' (' + LANGS[l]['audience'] + ')' for l in langs)}.
Each video will be published in both languages from one script, using free stock footage, AI narration and bold captions.
Style: {ctx.params.get('style', 'faceless, fast cuts, bold captions, calm narration')}.
{f'The owner is interested in: {focus}.' if focus else ''}

Use web search to check current demand and competition for Arabic and French Shorts (2026), typical RPM by niche,
and what successful faceless channels in these languages do. {breadth}

Score each niche 1-10 on: demand, competition (10 = little competition), monetization, faceless_fit
(can free stock footage + narration carry it?), copyright_safety (10 = no reliance on films, music, sports or brand footage).
total = weighted average: demand 0.25, competition 0.2, monetization 0.2, faceless_fit 0.2, copyright_safety 0.15.
Rank by total, best first. Cite concrete evidence (URLs, numbers) for each niche.

{evidence}

{ctx.revision_notes()}"""
        ctx.progress(45)
        result = await ctx.llm.ask(prompt, schema=SCHEMA, tools=["WebSearch", "WebFetch"])
        niches = sorted(result["niches"], key=lambda n: -n["total"])
        ctx.progress(90)

        out = ctx.write_json("niches.json", {"niches": niches})
        md = ["# Niche ranking", ""]
        for i, n in enumerate(niches, 1):
            s = n["scores"]
            md += [f"## {i}. {n['name']} (score {n['total']:.1f}, best for: {n['best_language']})", n["summary"], "",
                   f"demand {s['demand']} · competition {s['competition']} · monetization {s['monetization']} · "
                   f"faceless fit {s['faceless_fit']} · copyright safety {s['copyright_safety']}",
                   f"Example topics: {'; '.join(n['example_topics'])}", f"Risks: {n['risks']}",
                   "Evidence:", *[f"- {e}" for e in n["evidence"]], ""]
        ctx.path("niches.md").write_text("\n".join(md), encoding="utf-8")
        ctx.offer_choices([{
            "id": n["id"], "label": f"{i}. {n['name']} ({n['total']:.1f}/10)",
            "detail": f"{n['summary']}\nExamples: {'; '.join(n['example_topics'][:3])}\nRisks: {n['risks']}",
        } for i, n in enumerate(niches, 1)])
        return {"ranking": "niches.md", "data": out}
