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
        ar_tag_note = "; Arabic hashtags in Arabic for the ar version" if "ar" in langs else ""
        prompt = f"""Write YouTube Shorts packaging for {names(langs)}.
How each language is written:
{describe(langs)}

VIDEO TITLE (working): {script['title']}
NICHE: {ctx.params.get('niche')}
FULL NARRATION:
{json.dumps(narration, ensure_ascii=False, indent=1)}

For each language, write natively (not a literal translation):
- title: max 55 characters (so it never truncates on mobile Shorts feed), strong curiosity gap ("Why Your Brain...", "The Hidden Trick..."), accurate to the video
- description: 3-4 short lines; Line 1 MUST be a quick relatable question that sparks viewer comments (e.g., "Has this ever happened to you? 👇"); no links; no claims the video does not make
- hashtags: 4-6, always include #Shorts first plus high-volume niche hashtags{ar_tag_note}
- tags: 10-15 high-intent search phrases people actually type on YouTube
- thumbnail_text: 2-4 words, high-contrast curiosity punchline
Avoid trademarked names, celebrity names and anything sensational or misleading.

{ctx.revision_notes()}"""
        meta = await ctx.llm.ask(prompt, schema=lang_schema(langs, value_schema=LANG_META))
        for l in langs:
            if not any(h.lower() == "#shorts" for h in meta[l]["hashtags"]):
                meta[l]["hashtags"].append("#Shorts")
            meta[l]["title"] = meta[l]["title"][:100]
        ctx.progress(55)
        outputs = {"metadata": ctx.write_json("metadata.json", meta)}

        bg_path = ctx.path("thumb_src.png")
        used_banana = False
        if ctx.strategy == "banana_thumbnail" and llm_mod.api_key_available() and hasattr(ctx.llm, "generate_image"):
            try:
                hook_scene = script["scenes"][0]["visual"]["description"]
                art_prompt = (
                    f"Eye-catching vertical 9:16 YouTube Short thumbnail background for '{script['title']}'. "
                    f"Visual concept: {hook_scene}. Dramatic lighting, high contrast, vivid colors, clean dark focal area in the center "
                    "for bold headline text overlay. Do NOT include any text, letters, numbers, logos, or celebrity faces. "
                    + IMAGE_PROMPT_RULE
                )
                await ctx.llm.generate_image(art_prompt, bg_path, aspect_ratio="9:16", size=(1080, 1920))
                used_banana = True
            except Exception as e:  # noqa: BLE001 - fall back to video frame
                ctx.log(f"Nano Banana thumbnail background failed ({e}); using scene_01 frame instead", "warning")
        if not used_banana:
            bg_path = ctx.path("thumb_src.jpg")
            await ffmpeg.frame_at(ctx.run_dir / visuals[0], bg_path, ctx.run_dir, at=1.0)

        for l in langs:
            with Image.open(bg_path) as src_im:
                img = src_im.convert("RGB").resize((1080, 1920))
            if ctx.strategy != "plain_thumbnail":
                img = ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(1.2)).enhance(1.08)
            shade = Image.new("L", (1, 1920))
            for y in range(1920):  # darken the middle band where the text sits
                shade.putpixel((0, y), int(170 * max(0.0, 1 - abs(y - 960) / 700)))
            img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, shade.resize(img.size))
            text.draw_block(img, meta[l]["thumbnail_text"], l, size=150, y_center=900, max_width=940,
                            fill=(255, 229, 0), stroke_width=12)
            bar = ImageDraw.Draw(img)
            bar.rectangle([390, 1180, 690, 1196], fill=(255, 229, 0))
            path = f"thumbnail_{l}.png"
            img.save(ctx.path(path))
            if len(langs) == 1:
                shutil.copy2(ctx.run_dir / path, ctx.run_dir / "thumbnail.png")
            outputs[f"thumbnail_{l}"] = path
        bg_path.unlink(missing_ok=True)
        return outputs
