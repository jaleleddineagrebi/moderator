import json

from moderator.engine.agent import Agent, StepContext
from moderator.tools import history, youtube
from moderator.tools.languages import describe, names

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ideas"],
    "properties": {"ideas": {"type": "array", "minItems": 3, "maxItems": 3, "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "title", "angle", "hook", "keywords", "reason", "sources"],
        "properties": {
            "id": {"type": "string", "description": "short slug"},
            "title": {"type": "string", "description": "working title in English"},
            "angle": {"type": "string", "description": "what the video shows and why it surprises, 1-2 sentences"},
            "hook": {"type": "object", "additionalProperties": False, "required": ["ar", "fr"],
                     "properties": {"ar": {"type": "string"}, "fr": {"type": "string"}},
                     "description": "opening line, under 3 seconds when spoken"},
            "keywords": {"type": "array", "items": {"type": "string"}, "description": "search keywords (en, ar, fr)"},
            "reason": {"type": "string", "description": "why this will perform now, with evidence"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
    }}},
}


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        p = ctx.params
        niche = p.get("niche")
        if not niche:
            raise ValueError("No niche set. Run the niche_discovery workflow first, or pass -p niche=\"...\"")
        topic = p.get("topic")
        langs = p.get("languages", ["ar", "fr"])
        ctx.set_inputs(niche=niche, topic=topic, languages=langs)

        evidence = ""
        if ctx.strategy == "web_and_youtube" and youtube.available():
            ctx.log("Checking what performed in the niche over the last 14 days")
            data = {}
            for lang in langs:
                try:
                    data[lang] = await youtube.top_recent_shorts(topic or niche, lang, days=14, limit=10)
                except Exception as e:  # noqa: BLE001 - evidence is optional
                    ctx.log(f"YouTube lookup failed ({lang}): {e}", "warning")
            evidence = "TOP RECENT SHORTS IN THE NICHE:\n" + json.dumps(data, ensure_ascii=False)[:15000]
        ctx.progress(25)

        done_before = history.recent()
        avoid = ("ALREADY COVERED (do not propose these or close variations):\n"
                 + "\n".join(f"- {r['title']}" for r in done_before)) if done_before else ""
        tools = [] if ctx.strategy == "no_web" else ["WebSearch", "WebFetch"]
        prompt = f"""You are a YouTube Shorts trend researcher for a faceless channel.
Niche: {niche}. {p.get('niche_summary', '')}
{f'Requested topic: {topic}.' if topic else 'Pick topics yourself.'}
Audience: {names(langs)} speakers. One script is narrated in each language. How each language is written:
{describe(langs)}
Style: {p.get('style')}.

{'Use web search to find what is trending or newly discussed in this niche right now.' if tools else 'Use your own knowledge (web search is unavailable).'}
Propose exactly 3 video ideas, ranked best first. Each must:
- work as a 45-55 second Short with free stock footage (no film clips, brands, celebrities, or copyrighted characters)
- appeal to both Arabic and French audiences (avoid topics sensitive in MENA: religion debates, politics, alcohol, dating)
- have a strong hook that stops scrolling in under 3 seconds, written natively in each language as described above
- be factually solid (prefer well-documented facts; note sources)

{evidence}

{avoid}

{ctx.revision_notes()}"""
        result = await ctx.llm.ask(prompt, schema=SCHEMA, tools=tools)
        ideas = result["ideas"]
        ctx.progress(90)

        out = ctx.write_json("ideas.json", {"niche": niche, "ideas": ideas})
        md = [f"# Video ideas: {niche}", ""]
        for i, idea in enumerate(ideas, 1):
            md += [f"## {i}. {idea['title']}", idea["angle"], "", f"Hook (ar): {idea['hook']['ar']}",
                   f"Hook (fr): {idea['hook']['fr']}", f"Why now: {idea['reason']}",
                   f"Keywords: {', '.join(idea['keywords'])}", *[f"- {s}" for s in idea["sources"]], ""]
        ctx.path("ideas.md").write_text("\n".join(md), encoding="utf-8")
        ctx.offer_choices([{
            "id": idea["id"], "label": f"{i}. {idea['title']}",
            "detail": f"{idea['angle']}\nHook (fr): {idea['hook']['fr']}\nHook (ar): {idea['hook']['ar']}\nWhy: {idea['reason']}",
        } for i, idea in enumerate(ideas, 1)])
        return {"ideas": "ideas.md", "data": out}
