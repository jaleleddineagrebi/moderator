import json

from moderator.engine.agent import Agent, StepContext
from moderator.tools import history
from moderator.tools.visual_rules import PEOPLE_RULE
from moderator.tools.languages import LANGS, describe, lang_schema, names, normalize_langs

SEO = {  # packaging data written in the same call, so the packaging step needs no LLM call of its own
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "question", "hashtags", "tags"],
    "properties": {
        "title": {"type": "string", "description": "published title, max 55 characters, curiosity gap, accurate"},
        "question": {"type": "string", "description": "first description line: a short relatable question that invites comments"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "description": "3-5 niche hashtags, without #Shorts"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "8-12 search phrases people type"},
    },
}

BUDGET_SECONDS = (32, 46)  # crisp high-retention Shorts sweet spot (~34-44s final video; >90% completion rate)


def make_schema(langs: list[str]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "seo", "scenes"],
        "properties": {
            "title": {"type": "string", "description": "working title in English"},
            "seo": lang_schema(langs, value_schema=SEO, description="YouTube/TikTok packaging per language"),
            "scenes": {"type": "array", "minItems": 5, "maxItems": 9, "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["vo", "on_screen", "visual"],
                "properties": {
                    "vo": lang_schema(langs, description="narration for this scene"),
                    "on_screen": lang_schema(langs, description="bold headline text, max 5 words"),
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
        langs = normalize_langs(p.get("languages"))
        ctx.set_inputs(idea=full_idea["title"], languages=langs, comment_at_selection=ctx.decision("A")["comment"])
        history.record(ctx.store.data["run_id"], full_idea["title"], full_idea["angle"])

        budget = {lang: tuple(round(s * LANGS[lang]["words_per_second"]) for s in BUDGET_SECONDS) for lang in langs}
        if ctx.strategy == "tighter_word_budget":
            budget = {lang: (round(lo * 1.03), round(hi * 0.95)) for lang, (lo, hi) in budget.items()}
        scenes_hint = "5-6 scenes" if ctx.strategy == "simpler_structure" else "6-8 scenes"

        previous = ""
        if ctx.feedback and (ctx.run_dir / "script.json").exists():
            previous = "PREVIOUS VERSION (revise it, keep what works):\n" + (ctx.run_dir / "script.json").read_text(encoding="utf-8")

        word_ranges = "; ".join(f"{LANGS[l]['name']} {lo}-{hi} words" for l, (lo, hi) in budget.items())
        multi_note = ("Write each language natively; do not translate word for word. All versions must say the same facts in the same scene order."
                      if len(langs) > 1 else "Write natively and conversationally.")
        schema = make_schema(langs)
        prompt = f"""Write a YouTube Short script in {names(langs)}.

IDEA: {json.dumps(full_idea, ensure_ascii=False)}
{f"Owner's note when picking it: {ctx.decision('A')['comment']}" if ctx.decision('A')['comment'] else ''}
NICHE: {p.get('niche')}
STYLE: {p.get('style')}

Rules:
- Total narration word count (all scenes together): {word_ranges}. Aim for the crisp 34-42 second sweet spot so viewers watch 100%+ of the Short.
- {scenes_hint}. Scene 1 is an instant pattern-interrupt hook: spoken in under 2.5 seconds (max 7 words), starting mid-thought ("You...", a shocking contrast, or an immediate relatable moment — NEVER "Did you know").
- Each scene covers one fast beat (5-6s max per scene) with open curiosity loops so viewers cannot swipe away.
- Seamless infinite-loop ending: the final scene delivers the payoff and ends with a bridge phrase that flows naturally right back into Scene 1's opening line (do NOT say "Follow for more" or "Subscribe", which makes viewers swipe away early and drops completion rate).
- Languages (field key = how to write it):
{describe(langs)}
  {multi_note}
- on_screen: a punchy headline per scene, max 5 words.
- visual: describe dynamic moving B-roll footage findable on free stock video sites (Pexels/Pixabay/Commons). No logos, brands, celebrities, film characters.
  People rule for every visual and search term: {PEOPLE_RULE} Never put "woman", "girl" or similar in search_terms.
  Set `prefer` to `"video"` so scenes use moving video clips rather than static images.
  Provide 3-4 short (2-3 word) English `search_terms` using concrete filmable subjects with motion ("person scrolling phone", "crowded crosswalk", "clock hands moving"); make the last term a broad 2-word B-roll query ("city street", "ocean waves", "walking crowd") guaranteed to match stock video libraries.
- Facts must be accurate. No medical, financial or religious claims that could mislead.
- seo (per language, written natively): title max 55 characters with a strong curiosity gap and no false claims; question = a relatable one-line question that sparks comments; 3-5 niche hashtags (no #Shorts); 8-12 search tags. No trademarks or celebrity names.

{previous}

{ctx.revision_notes()}"""
        ctx.progress(10)
        script = await ctx.llm.ask(prompt, schema=schema)
        est = estimate(script, langs)
        ctx.log("Estimated narration: " + ", ".join(f"{l} {v}s" for l, v in est.items()))

        if not all(BUDGET_SECONDS[0] - 2 <= v <= BUDGET_SECONDS[1] + 1 for v in est.values()):
            ctx.log("Length outside 45-55s, asking for a fix", "warning")
            ctx.progress(55)
            fix = (f"{prompt}\n\nYOUR DRAFT (estimated narration seconds: {est}; target {BUDGET_SECONDS[0]}-{BUDGET_SECONDS[1]}s each). "
                   f"Adjust the narration length to fit, keeping everything else:\n{json.dumps(script, ensure_ascii=False)}")
            script = await ctx.llm.ask(fix, schema=schema)
            est = estimate(script, langs)
            ctx.log("Revised estimate: " + ", ".join(f"{l} {v}s" for l, v in est.items()))
            if not all(BUDGET_SECONDS[0] - 4 <= v <= BUDGET_SECONDS[1] + 2 for v in est.values()):
                raise ValueError(f"script length still off target: {est}")

        for i, s in enumerate(script["scenes"], 1):
            s["id"] = f"scene_{i:02d}"
        script.update(idea_id=full_idea["id"], languages=langs, estimated_seconds=est)
        out = ctx.write_json("script.json", script)

        md = [f"# {script['title']}", "Estimated narration: " + " · ".join(f"{l} {v}s" for l, v in est.items()), ""]
        for s in script["scenes"]:
            md.append(f"## {s['id']} · {s['visual']['description']}")
            for code in langs:
                md.append(f"{code.upper()}  [{s['on_screen'][code]}]  {s['vo'][code]}")
            md.append("")
        ctx.path("script.md").write_text("\n".join(md), encoding="utf-8")
        return {"script": "script.md", "data": out}
