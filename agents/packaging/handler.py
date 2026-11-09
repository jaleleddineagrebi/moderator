import json
import shutil

from PIL import Image, ImageDraw, ImageEnhance

from moderator.engine import llm as llm_mod
from moderator.engine.agent import Agent, StepContext
from moderator.tools import ffmpeg, text
from moderator.tools.visual_rules import IMAGE_PROMPT_RULE
from moderator.tools.languages import describe, lang_schema, names, normalize_langs

LANG_META = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "description", "hashtags", "tags", "thumbnail_text"],
    "properties": {
        "title": {"type": "string", "description": "max 55 characters, curiosity-driven, no clickbait lies"},
        "description": {"type": "string", "description": "2-4 short lines; first line restates the hook"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "description": "3-6 hashtags including #Shorts"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "8-15 search tags"},
        "thumbnail_text": {"type": "string", "description": "2-4 words, huge on the thumbnail"},
    },
}


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        script = ctx.read_json(ctx.upstream("script")["data"])
        visuals = ctx.upstream("visuals")["scenes"]
        langs = normalize_langs(ctx.params.get("languages"))
        ctx.set_inputs(script=ctx.upstream("script")["data"], languages=langs,
                       strategy=ctx.strategy, thumbnail_source=visuals[0])

        narration = {l: " ".join(s["vo"][l] for s in script["scenes"]) for l in langs}
        is_long = str(ctx.params.get("format") or "short").lower() == "long"
        ar_tag_note = "; Arabic hashtags in Arabic for the ar version" if "ar" in langs else ""
        prompt = f"""Write high-CTR YouTube {'Deep-Dive video' if is_long else 'Shorts'} packaging for {names(langs)}.
How each language is written:
{describe(langs)}

VIDEO TITLE (working): {script['title']}
NICHE: {ctx.params.get('niche')}
FULL NARRATION:
{json.dumps(narration, ensure_ascii=False, indent=1)}

For each language, write natively (not a literal translation):
- title: max {'65' if is_long else '50'} characters (so it never truncates on mobile feeds), extreme curiosity gap + emotional stakes ("Why Your Brain...", "If Someone Does THIS...", "90% of People Fail This Test"), accurate to the video
- description: 3-4 short lines; Line 1 MUST be an interactive binary comment trigger that boosts algorithm engagement (e.g., "Did this work on you? Comment YES or NO below 👇"); the last line MUST be a high-converting Subscribe call-to-action (e.g. "🔔 Subscribe for your daily 30-second brain test 👇", in FR: "🔔 Abonne-toi pour ton test mental quotidien 👇", in AR: "🔔 اشترك الآن لاختبار عقلك يومياً 👇"); no links; no claims the video does not make
- hashtags: 4-6, {'high-volume niche hashtags' if is_long else 'always include #Shorts first plus high-volume niche hashtags'}{ar_tag_note}
- tags: 12-15 high-intent search phrases people actually type on YouTube
- thumbnail_text: 2-4 words, huge high-contrast curiosity punchline (e.g. "DON'T BLINK", "FAKE SMILE?", "BRAIN GLITCH")
Avoid trademarked names, celebrity names and anything sensational or misleading.

{ctx.revision_notes()}"""
        meta = await ctx.llm.ask(prompt, schema=lang_schema(langs, value_schema=LANG_META))
        for l in langs:
            if not is_long and not any(h.lower() == "#shorts" for h in meta[l]["hashtags"]):
                meta[l]["hashtags"].append("#Shorts")
            meta[l]["title"] = meta[l]["title"][:100]
            meta[l]["format"] = "long" if is_long else "short"
        ctx.progress(55)
        outputs = {"metadata": ctx.write_json("metadata.json", meta)}

        thumb_size = (1920, 1080) if is_long else (1080, 1920)
        thumb_ar = "16:9" if is_long else "9:16"
        bg_path = ctx.path("thumb_src.png")
        used_banana = False
        if ctx.strategy == "banana_thumbnail" and llm_mod.api_key_available() and hasattr(ctx.llm, "generate_image"):
            try:
                hook_scene = script["scenes"][0]["visual"]["description"]
                art_prompt = (
                    f"Eye-catching {thumb_ar} YouTube thumbnail background for '{script['title']}'. "
                    f"Visual concept: {hook_scene}. Dramatic lighting, high contrast, vivid colors, clean dark focal area in the center "
                    "for bold headline text overlay. Do NOT include any text, letters, numbers, logos, or celebrity faces. "
                    + IMAGE_PROMPT_RULE
                )
                await ctx.llm.generate_image(art_prompt, bg_path, aspect_ratio=thumb_ar, size=thumb_size)
                used_banana = True
            except Exception as e:  # noqa: BLE001 - fall back to video frame
                ctx.log(f"Nano Banana thumbnail background failed ({e}); using scene_01 frame instead", "warning")
        if not used_banana:
            bg_path = ctx.path("thumb_src.jpg")
            await ffmpeg.frame_at(ctx.run_dir / visuals[0], bg_path, ctx.run_dir, at=1.0)

        tw, th = thumb_size
        for l in langs:
            with Image.open(bg_path) as src_im:
                img = src_im.convert("RGB").resize(thumb_size)
            if ctx.strategy != "plain_thumbnail":
                img = ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(1.24)).enhance(1.1)
            shade = Image.new("L", (1, th))
            for y in range(th):  # darken the middle band where the text sits
                shade.putpixel((0, y), int(175 * max(0.0, 1 - abs(y - th // 2) / (th * 0.36))))
            img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, shade.resize(img.size))
            text.draw_block(img, meta[l]["thumbnail_text"], l, size=140 if is_long else 150,
                            y_center=int(th * 0.47), max_width=int(tw * 0.86),
                            fill=(255, 229, 0), stroke_width=12)
            bar = ImageDraw.Draw(img)
            bar_y = int(th * 0.62)
            bar.rectangle([tw // 2 - 150, bar_y, tw // 2 + 150, bar_y + 16], fill=(255, 229, 0))
            path = f"thumbnail_{l}.png"
            img.save(ctx.path(path))
            if len(langs) == 1:
                shutil.copy2(ctx.run_dir / path, ctx.run_dir / "thumbnail.png")
            outputs[f"thumbnail_{l}"] = path
        bg_path.unlink(missing_ok=True)
        return outputs
