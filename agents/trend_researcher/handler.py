import json

from moderator.engine.agent import Agent, StepContext
from moderator.tools import history, youtube
from moderator.tools.languages import describe, lang_schema, names, normalize_langs, sensitivity_guidance


def make_schema(langs: list[str]) -> dict:
    return {
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
                "hook": lang_schema(langs, description="opening line, under 3 seconds when spoken"),
                "keywords": {"type": "array", "items": {"type": "string"}, "description": f"search keywords ({', '.join(langs)})"},
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
            raise ValueError('No niche set. Run the niche_discovery workflow first, or pass -p niche="..."')
        topic = p.get("topic")
        langs = normalize_langs(p.get("languages"))
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
        is_long = str(p.get("format") or "short").lower() == "long"
        format_instructions = (
            """Propose exactly 3 high-CTR 16:9 Long-Form Deep-Dive video ideas (3 to 4 minutes each), ranked best first for YouTube Home Page (Browse) impressions & subscriber conversion. Each must:
- use a proven high-CTR multi-part or deep-dive structure (e.g. "7 Psychological Tricks That Work On 99% of People", "5 Subtle Signs Someone Is Secretly Manipulating You", "Why Your Brain Sabotages You Every Night — And The 3-Step Fix")
- work with dynamic stock video footage and AI visuals (no film clips, brands, celebrities, or copyrighted characters)
- appeal to {langs} audiences ({sens})
- have a gripping 5-second cold open hook that promises a life-changing mental edge or self-discovery test
- be factually solid (backed by real behavioral science; note sources)"""
            if is_long else
            """Propose exactly 3 viral YouTube Short ideas, ranked best first for 80%+ Viewed-vs-Swiped-Away (VVSA), >105% Average Percentage Viewed (APV), and explosive subscriber & comment conversion.
CRITICAL — NEVER propose dry textbook/encyclopedia lectures. Every idea MUST use one of these 4 Proven Viral Archetypes:
1. INTERACTIVE BRAIN TEST / LIVE PREDICTION: The viewer performs a 3-second test while watching ("Pick a number from 1 to 9 right now...", "Try this 4-second memory test—92% fail"). Forces 100%+ watch time and floods the comments.
2. SOCIAL POWER & MICRO-BEHAVIOR DECODING: High-status, practical social survival secrets ("The 3-second silence trick that forces anyone to respect you", "Watch someone's feet when they talk to you—here's why").
3. HYPER-RELATABLE BRAIN GLITCHES: Calling out a weird thing everyone secretly does ("Why your brain invents fake arguments in the shower", "Why you forget someone's name 2 seconds after they say it").
4. FORBIDDEN / REVERSE PSYCHOLOGY PARADOXES: Counter-intuitive rules ("Never say 'No Problem'—say these 2 words instead", "Why asking an enemy for a small favor forces their brain to like you").

Each idea must:
- work as a fast-paced 34-42 second Short with dynamic free stock video footage (no film clips, brands, celebrities, or copyrighted characters)
- appeal to {langs} audiences ({sens})
- have an instant pattern-interrupt hook (under 2.2 seconds / max 7 words) starting with a direct challenge, command, or "You..." truth — NEVER "Did you know" or academic jargon in the first 3 seconds
- include a built-in comment trigger & subscribe angle in `angle`
- be factually solid (prefer well-documented behavioral science; note sources)"""
        ).format(langs=names(langs), sens=sensitivity_guidance(langs))

        prompt = f"""You are a 10M+ view YouTube growth strategist & viral trend researcher for a faceless channel.
Niche: {niche}. {p.get('niche_summary', '')}
{f'Requested topic: {topic}.' if topic else 'Pick the highest-velocity viral topics yourself.'}
Audience: {names(langs)} speakers. How each language is written:
{describe(langs)}
Style: {p.get('style')}.

{'Use web search to find what is trending or going viral in this niche right now.' if tools else 'Use your own knowledge (web search is unavailable).'}
{format_instructions}

{evidence}

{avoid}

{ctx.revision_notes()}"""
        result = await ctx.llm.ask(prompt, schema=make_schema(langs), tools=tools)
        ideas = result["ideas"]
        ctx.progress(90)

        out = ctx.write_json("ideas.json", {"niche": niche, "languages": langs, "ideas": ideas})
        md = [f"# Video ideas: {niche}", ""]
        for i, idea in enumerate(ideas, 1):
            hooks_md = [f"Hook ({code}): {idea['hook'][code]}" for code in langs]
            md += [f"## {i}. {idea['title']}", idea["angle"], "", *hooks_md,
                   f"Why now: {idea['reason']}", f"Keywords: {', '.join(idea['keywords'])}",
                   *[f"- {s}" for s in idea["sources"]], ""]
        ctx.path("ideas.md").write_text("\n".join(md), encoding="utf-8")
        ctx.offer_choices([{
            "id": idea["id"],
            "label": f"{i}. {idea['title']}",
            "detail": "\n".join([
                idea["angle"],
                *(f"Hook ({code}): {idea['hook'][code]}" for code in langs),
                f"Why: {idea['reason']}",
            ]),
        } for i, idea in enumerate(ideas, 1)])
        return {"ideas": "ideas.md", "data": out}
