import json

from moderator.engine.agent import Agent, StepContext
from moderator.tools import history
from moderator.tools.languages import LANGS, describe, names

BUDGET_SECONDS = (43, 52)  # narration length; leaves room for scene pauses and the outro tail (video target 45-55s)

BILINGUAL = {"type": "object", "additionalProperties": False, "required": ["ar", "fr"],
             "properties": {"ar": {"type": "string"}, "fr": {"type": "string"}}}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "scenes"],
    "properties": {
        "title": {"type": "string", "description": "working title in English"},
        "scenes": {"type": "array", "minItems": 5, "maxItems": 9, "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["vo", "on_screen", "visual"],
            "properties": {
                "vo": {**BILINGUAL, "description": "narration for this scene"},
                "on_screen": {**BILINGUAL, "description": "bold headline text, max 5 words"},
                "visual": {"type": "object", "additionalProperties": False,
                           "required": ["description", "search_terms", "prefer"],
                           "properties": {
                               "description": {"type": "string"},
                               "search_terms": {"type": "array", "items": {"type": "string"},
                                                "description": "2-4 short English stock-footage queries, most specific first"},
                               "prefer": {"type": "string", "enum": ["video", "photo"]},
                           }},
            },
        }},
    },
}


def estimate(script: dict, langs: list[str]) -> dict[str, float]:
    return {lang: round(sum(len(s["vo"][lang].split()) for s in script["scenes"]) / LANGS[lang]["words_per_second"], 1)
            for lang in langs}


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        p = ctx.params
        idea = ctx.chosen_option("A")
        ideas = ctx.read_json(ctx.upstream("research")["data"])["ideas"]
        full_idea = next((i for i in ideas if idea and i["id"] == idea["id"]), ideas[0])
        ctx.set_inputs(idea=full_idea["title"], comment_at_selection=ctx.decision("A")["comment"])
        history.record(ctx.store.data["run_id"], full_idea["title"], full_idea["angle"])

        langs = p.get("languages", ["ar", "fr"])
        budget = {lang: tuple(round(s * LANGS[lang]["words_per_second"]) for s in BUDGET_SECONDS) for lang in langs}
        if ctx.strategy == "tighter_word_budget":
            budget = {lang: (round(lo * 1.03), round(hi * 0.95)) for lang, (lo, hi) in budget.items()}
        scenes_hint = "5-6 scenes" if ctx.strategy == "simpler_structure" else "6-8 scenes"

        previous = ""
        if ctx.feedback and (ctx.run_dir / "script.json").exists():
            previous = "PREVIOUS VERSION (revise it, keep what works):\n" + (ctx.run_dir / "script.json").read_text(encoding="utf-8")

        word_ranges = "; ".join(f"{LANGS[l]['name']} {lo}-{hi} words" for l, (lo, hi) in budget.items())
        prompt = f"""Write a YouTube Short script, narrated separately in {names(langs)}.

IDEA: {json.dumps(full_idea, ensure_ascii=False)}
{f"Owner's note when picking it: {ctx.decision('A')['comment']}" if ctx.decision('A')['comment'] else ''}
NICHE: {p.get('niche')}
STYLE: {p.get('style')}

Rules:
- Total narration word count (all scenes together): {word_ranges}. Stay inside these ranges: the video must end up 45-55 seconds.
- {scenes_hint}. Scene 1 is the hook: spoken in under 3 seconds (max 8 words), creates curiosity immediately.
- Each scene covers one beat; the last scene pays off the hook and ends with a short call to follow.
- Languages (field key = how to write it):
{describe(langs)}
  Write each language natively; do not translate word for word. Both versions must say the same facts in the same scene order.
- on_screen: a punchy headline per scene, max 5 words, same meaning in both languages.
- visual: describe footage findable on free stock sites (Pexels/Pixabay). No logos, brands, celebrities, film characters.
  search_terms in English, concrete nouns ("honeybee on flower macro", not "nature's wonder").
- Facts must be accurate. No medical, financial or religious claims that could mislead.

{previous}

{ctx.revision_notes()}"""
        ctx.progress(10)
        script = await ctx.llm.ask(prompt, schema=SCHEMA)
        est = estimate(script, langs)
        ctx.log("Estimated narration: " + ", ".join(f"{l} {v}s" for l, v in est.items()))

        if not all(BUDGET_SECONDS[0] - 2 <= v <= BUDGET_SECONDS[1] + 1 for v in est.values()):
            ctx.log("Length outside 45-55s, asking for a fix", "warning")
            ctx.progress(55)
            fix = (f"{prompt}\n\nYOUR DRAFT (estimated narration seconds: {est}; target {BUDGET_SECONDS[0]}-{BUDGET_SECONDS[1]}s each). "
                   f"Adjust the narration length to fit, keeping everything else:\n{json.dumps(script, ensure_ascii=False)}")
            script = await ctx.llm.ask(fix, schema=SCHEMA)
            est = estimate(script, langs)
            ctx.log("Revised estimate: " + ", ".join(f"{l} {v}s" for l, v in est.items()))
            if not all(BUDGET_SECONDS[0] - 4 <= v <= BUDGET_SECONDS[1] + 2 for v in est.values()):
                raise ValueError(f"script length still off target: {est}")

        for i, s in enumerate(script["scenes"], 1):
            s["id"] = f"scene_{i:02d}"
        script.update(idea_id=full_idea["id"], estimated_seconds=est)
        out = ctx.write_json("script.json", script)

        md = [f"# {script['title']}", "Estimated narration: " + " · ".join(f"{l} {v}s" for l, v in est.items()), ""]
        for s in script["scenes"]:
            md += [f"## {s['id']} · {s['visual']['description']}",
                   f"FR  [{s['on_screen']['fr']}]  {s['vo']['fr']}",
                   f"AR  [{s['on_screen']['ar']}]  {s['vo']['ar']}", ""]
        ctx.path("script.md").write_text("\n".join(md), encoding="utf-8")
        return {"script": "script.md", "data": out}
