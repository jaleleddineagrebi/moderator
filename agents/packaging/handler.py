import json

from PIL import Image, ImageDraw, ImageEnhance

from moderator.engine.agent import Agent, StepContext
from moderator.tools import ffmpeg, text
from moderator.tools.languages import describe, names

LANG_META = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "description", "hashtags", "tags", "thumbnail_text"],
    "properties": {
        "title": {"type": "string", "description": "max 70 characters, curiosity-driven, no clickbait lies"},
        "description": {"type": "string", "description": "2-4 short lines; first line restates the hook"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "description": "3-6 hashtags including #Shorts"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "8-15 search tags"},
        "thumbnail_text": {"type": "string", "description": "2-4 words, huge on the thumbnail"},
    },
}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ar", "fr"], "properties": {"ar": LANG_META, "fr": LANG_META}}


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        script = ctx.read_json(ctx.upstream("script")["data"])
        visuals = ctx.upstream("visuals")["scenes"]
        langs = ctx.params.get("languages", ["ar", "fr"])
        ctx.set_inputs(script=ctx.upstream("script")["data"], thumbnail_source=visuals[0])

        narration = {l: " ".join(s["vo"][l] for s in script["scenes"]) for l in langs}
        prompt = f"""Write YouTube Shorts packaging for one video published in two versions: {names(langs)}.
How each language is written:
{describe(langs)}

VIDEO TITLE (working): {script['title']}
NICHE: {ctx.params.get('niche')}
FULL NARRATION:
{json.dumps(narration, ensure_ascii=False, indent=1)}

For each language, write natively (not a literal translation):
- title: max 70 characters, makes people curious, accurate to the video
- description: 2-4 short lines; no links; no claims the video does not make
- hashtags: 3-6, always include #Shorts; Arabic hashtags in Arabic for the ar version
- tags: 8-15 search phrases people actually type
- thumbnail_text: 2-4 words, punchy
Avoid trademarked names, celebrity names and anything sensational or misleading.

{ctx.revision_notes()}"""
        meta = await ctx.llm.ask(prompt, schema=SCHEMA)
        for l in langs:
            if not any(h.lower() == "#shorts" for h in meta[l]["hashtags"]):
                meta[l]["hashtags"].append("#Shorts")
            meta[l]["title"] = meta[l]["title"][:100]
        ctx.progress(60)
        outputs = {"metadata": ctx.write_json("metadata.json", meta)}

        frame = ctx.path("thumb_src.jpg")
        await ffmpeg.frame_at(ctx.run_dir / visuals[0], frame, ctx.run_dir, at=1.0)
        for l in langs:
            img = Image.open(frame).convert("RGB").resize((1080, 1920))
            if ctx.strategy != "plain_thumbnail":
                img = ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(1.25)).enhance(1.1)
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
            outputs[f"thumbnail_{l}"] = path
        frame.unlink(missing_ok=True)
        return outputs
