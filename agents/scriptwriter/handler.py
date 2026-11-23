import json

from moderator.engine.agent import Agent, StepContext
from moderator.tools import history
from moderator.tools.visual_rules import PEOPLE_RULE
from moderator.tools.languages import LANGS, describe, lang_schema, names, normalize_langs

BUDGET_SECONDS = (32, 46)  # crisp high-retention Shorts sweet spot (~34-44s final video; >90% completion rate)
LONG_BUDGET_SECONDS = (240, 330)  # 4 to 5.5-minute Deep-Dive: enough watch time to matter, ~10-14 s per scene


def make_schema(langs: list[str], *, is_long: bool = False) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "scenes"],
        "properties": {
            "title": {"type": "string", "description": "working title in English"},
            "scenes": {"type": "array", "minItems": 18 if is_long else 5, "maxItems": 30 if is_long else 9, "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["vo", "on_screen", "visual"] + (["chapter"] if is_long else []),
                "properties": {
                    "chapter": {"type": "string",
                                "description": "long videos only: chapter title (2-5 words, no timestamp) on the FIRST scene of each chapter, empty string on every other scene"},
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

        is_long = str(p.get("format") or "short").lower() == "long"
        target_sec = LONG_BUDGET_SECONDS if is_long else BUDGET_SECONDS
        budget = {lang: tuple(round(s * LANGS[lang]["words_per_second"]) for s in target_sec) for lang in langs}
        if ctx.strategy == "tighter_word_budget":
            budget = {lang: (round(lo * 1.03), round(hi * 0.95)) for lang, (lo, hi) in budget.items()}
        if is_long:
            scenes_hint = "20-26 scenes"
        else:
            scenes_hint = "5-6 scenes" if ctx.strategy == "simpler_structure" else "6-8 scenes"

        previous = ""
        if ctx.feedback and (ctx.run_dir / "script.json").exists():
            previous = "PREVIOUS VERSION (revise it, keep what works):\n" + (ctx.run_dir / "script.json").read_text(encoding="utf-8")

        word_ranges = "; ".join(f"{LANGS[l]['name']} {lo}-{hi} words" for l, (lo, hi) in budget.items())
        multi_note = ("Write each language natively; do not translate word for word. All versions must say the same facts in the same scene order."
                      if len(langs) > 1 else "Write natively and conversationally.")
        schema = make_schema(langs, is_long=is_long)
        format_label = "4-5 Minute 16:9 YouTube Deep-Dive Video" if is_long else "Viral YouTube Short"
        structure_rules = (
            f"- Total narration word count (all scenes together): {word_ranges} (target {target_sec[0]}-{target_sec[1]}s, about 4-5 minutes).\n"
            f"- {scenes_hint}, 25-38 words of narration each (roughly 9-14 seconds per scene). Calm storyteller pacing: this is NOT a Short, do not rush.\n"
            "- STORY STRUCTURE, in this order:\n"
            "  1. COLD OPEN (scenes 1-2, under 20 s): a vivid, specific hook with real stakes, then a clear promise of what the viewer will understand or be able to do by the end. No greeting, no 'welcome back', no 'in this video'.\n"
            "  2. CONTEXT (1-2 scenes): why this matters to the viewer's own life, with one relatable everyday example.\n"
            "  3. BODY, 4-6 chapters. Each chapter = a surprising claim, how it works in plain language, a concrete example or mini-story, and a one-sentence takeaway. Order them so the most surprising one comes second to last.\n"
            "  4. OPEN LOOPS: finish every chapter by teasing the next one ('But the next reason is the one almost nobody notices...'), and plant in scene 2 a payoff that is only delivered near the end.\n"
            "  5. PATTERN INTERRUPT about every 40-60 seconds: a direct question to the viewer, a surprising number, a sharp contrast, or a 'try this right now' micro-task. Vary sentence length.\n"
            "  6. PAYOFF AND RECAP (2 scenes): deliver the promised payoff, then recap the key points in one breath.\n"
            "  7. CLOSE: ask ONE specific question for the comments, then one soft invitation to subscribe for the next deep dive. Never ask for likes or subscribes before the end.\n"
            "- `chapter`: put a short chapter title (2-5 words, for example 'Why it happens') on the first scene of each of the 5-8 chapters (scene 1 is 'Intro'), and an empty string on all other scenes. Chapters must be at least 25 seconds long.\n"
            "- Visual variety: set `prefer` to \"photo\" for about one scene in three (an AI-generated concept image, symbolic or diagram-like, for abstract ideas) and \"video\" for the rest (real moving footage)."
            if is_long else
            f"- Total narration word count (all scenes together): {word_ranges}. Aim for the crisp 34-42 second sweet spot so viewers watch 100%+ of the Short.\n"
            f"- {scenes_hint}. Scene 1 is an instant 0-2.2s scroll-stopping hook (max 6-7 words): start with a live test on the viewer ('Pick a number...', 'Don't blink...'), a brutal social truth ('If someone does THIS...'), or a direct 'You...' callout — NEVER 'Did you know' or textbook definitions.\n"
            "- Fast Retention Beats: each scene covers one crisp beat (4-5s max per scene). Scene 4 MUST be a Mid-Point Re-Hook ('But here is the creepy part...', 'Wait until you test the second one...') so viewers cannot swipe at the 15-second mark.\n"
            "- Subscriber + Comment Trigger (required in final scene): AFTER the payoff lands, include a 1-sentence interactive Subscribe + Comment challenge (e.g. 'Subscribe for tomorrow's brain test — and comment YES if this worked on you'). Set the final scene's `on_screen` to 'SUBSCRIBE 🔔' (in French: 'ABONNE-TOI 🔔', in Arabic: 'اشترك الآن 🔔').\n"
            "- Seamless Infinite-Loop Ending: end the final scene with a 3-5 word bridge clause ('...which is exactly why') that flows seamlessly back into Scene 1's first word."
        )
        prefer_rule = ('Set `prefer` as described in the visual variety rule above ("photo" = AI concept image, "video" = moving footage).'
                       if is_long else 'Set `prefer` to `"video"` so scenes use moving video clips rather than static images.')
        style_line = (f"{p.get('style')}. For this LONG video ignore any 'hyper-fast cuts' or 'punchy energetic' wording: use a calm, confident storyteller voice."
                      if is_long else p.get('style'))
        prompt = f"""Write a {format_label} script in {names(langs)}.

IDEA: {json.dumps(full_idea, ensure_ascii=False)}
{f"Owner's note when picking it: {ctx.decision('A')['comment']}" if ctx.decision('A')['comment'] else ''}
NICHE: {p.get('niche')}
STYLE: {style_line}

Rules:
{structure_rules}
- Languages (field key = how to write it):
{describe(langs)}
  {multi_note}
- on_screen: a punchy headline per scene, max 4-5 words.
- visual: describe dynamic moving B-roll footage findable on free stock video sites (Pexels/Pixabay/Commons). No logos, brands, celebrities, film characters.
  People rule for every visual and search term: {PEOPLE_RULE} Never put "woman", "girl" or similar in search_terms.
  {prefer_rule}
  Visual diversity requirement: Ensure each scene has completely distinct visual subjects, environments, and metaphors. Provide 3-4 short (2-3 word) English `search_terms` using concrete filmable subjects with motion tailored strictly to that scene's unique narrative beat (e.g. "person typing keyboard", "crowded metro train", "hourglass sand falling"). NEVER reuse the same search term across different scenes, and avoid repetitive clichés.
- Facts must be accurate. No medical, financial or religious claims that could mislead.

{previous}

{ctx.revision_notes()}"""
        ctx.progress(10)
        script = await ctx.llm.ask(prompt, schema=schema)
        est = estimate(script, langs)
        ctx.log("Estimated narration: " + ", ".join(f"{l} {v}s" for l, v in est.items()))

        tol_a, tol_b = (14, 22) if is_long else (2, 4)  # long scripts are harder to land exactly
        if not all(target_sec[0] - tol_a <= v <= target_sec[1] + tol_a for v in est.values()):
            ctx.log(f"Length outside {target_sec[0]}-{target_sec[1]}s, asking for a fix", "warning")
            ctx.progress(55)
            fix = (f"{prompt}\n\nYOUR DRAFT (estimated narration seconds: {est}; target {target_sec[0]}-{target_sec[1]}s each). "
                   f"Adjust the narration length to fit, keeping everything else:\n{json.dumps(script, ensure_ascii=False)}")
            script = await ctx.llm.ask(fix, schema=schema)
            est = estimate(script, langs)
            ctx.log("Revised estimate: " + ", ".join(f"{l} {v}s" for l, v in est.items()))
            if not all(target_sec[0] - tol_b <= v <= target_sec[1] + tol_b for v in est.values()):
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
