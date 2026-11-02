import asyncio
import colorsys
import random
import zlib

from PIL import Image, ImageDraw, ImageFilter

from moderator.engine.agent import Agent, StepContext
from moderator.tools import ffmpeg, stock

TIERS = ["stock_video", "stock_photo", "generated"]


def generated_background(path, seed: int) -> None:
    """Soft gradient with blurred light blobs: neutral, original, safe behind bold captions."""
    rnd = random.Random(seed)
    hue = rnd.random()
    top = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.55, 0.35))
    bottom = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.12) % 1, 0.65, 0.12))
    img = Image.new("RGB", (1080, 1920))
    draw = ImageDraw.Draw(img)
    for y in range(1920):
        k = y / 1919
        draw.line([(0, y), (1080, y)], fill=tuple(int(top[i] * (1 - k) + bottom[i] * k) for i in range(3)))
    glow = Image.new("RGB", (1080, 1920))
    gd = ImageDraw.Draw(glow)
    for _ in range(9):
        r = rnd.randint(120, 360)
        x, y = rnd.randint(-100, 1180), rnd.randint(-100, 2020)
        c = tuple(int(v * 255) for v in colorsys.hsv_to_rgb((hue + rnd.uniform(-0.1, 0.2)) % 1, 0.5, 0.9))
        gd.ellipse([x - r, y - r, x + r, y + r], fill=c)
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(120)), 0.35)
    img.save(path)


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        script = ctx.read_json(ctx.upstream("script")["data"])
        keys = stock.available()
        providers = [p for p in ("pexels", "pixabay") if keys[p]]
        start = TIERS.index(ctx.strategy) if ctx.strategy in TIERS else 0
        if not providers:
            ctx.log("No PEXELS_API_KEY or PIXABAY_API_KEY in .env: using generated backgrounds", "warning")
            start = TIERS.index("generated")
        ctx.set_inputs(script=ctx.upstream("script")["data"], providers=providers, starting_tier=TIERS[start])
        if ctx.feedback:
            ctx.log(f"Revision feedback: {ctx.feedback[-1]['comment']}")

        used: set[str] = set()
        licenses: list[dict] = []
        sem = asyncio.Semaphore(3)
        scenes = script["scenes"]
        done = 0

        async def produce(i: int, scene: dict) -> str:
            nonlocal done
            async with sem:
                out = ctx.path(f"assets/{scene['id']}.mp4")
                tiers = TIERS[start:]
                if scene["visual"].get("prefer") == "photo" and "stock_video" in tiers:
                    tiers = ["stock_photo", "stock_video", "generated"]
                for tier in tiers:
                    try:
                        lic = await self._tier(ctx, tier, scene, i, providers, used, out)
                    except Exception as e:  # noqa: BLE001 - fall through to the next tier
                        ctx.log(f"{scene['id']}: {tier} failed ({type(e).__name__}: {e})", "warning")
                        continue
                    if lic:
                        licenses.append({"scene": scene["id"], "tier": tier, **lic})
                        done += 1
                        ctx.progress(5 + 85 * done / len(scenes))
                        ctx.log(f"{scene['id']}: {tier} ({lic.get('provider', 'generated')})")
                        return out.relative_to(ctx.run_dir).as_posix()
                raise RuntimeError(f"no visual produced for {scene['id']}")

        clips = await asyncio.gather(*(produce(i, s) for i, s in enumerate(scenes)))
        licenses.sort(key=lambda x: x["scene"])
        lic_path = ctx.write_json("assets/licenses.json", licenses)
        sheet = await self._contact_sheet(ctx, clips)
        return {"contact_sheet": sheet, "scenes": clips, "licenses": lic_path}

    async def _tier(self, ctx, tier, scene, i, providers, used, out) -> dict | None:
        if tier == "generated":
            png = ctx.path(f"assets/raw/{scene['id']}.png")
            generated_background(png, seed=zlib.crc32(f"{ctx.store.data['run_id']}:{i}".encode()))
            await ffmpeg.still_to_clip(png, out, ctx.run_dir, seconds=10, zoom_in=i % 2 == 0)
            return {"provider": "generated", "license": "original work, no third-party rights"}
        for term in scene["visual"]["search_terms"]:
            for provider in providers:
                if tier == "stock_video":
                    results = await stock.search_videos(term, provider)
                else:
                    results = await stock.search_photos(term, provider)
                pick = next((r for r in results if r["page"] not in used), None)
                if not pick:
                    continue
                used.add(pick["page"])
                ext = "mp4" if tier == "stock_video" else "jpg"
                raw = ctx.path(f"assets/raw/{scene['id']}.{ext}")
                await stock.download(pick["url"], raw)
                if tier == "stock_video":
                    await ffmpeg.normalize_clip(raw, out, ctx.run_dir)
                else:
                    await ffmpeg.still_to_clip(raw, out, ctx.run_dir, seconds=10, zoom_in=i % 2 == 0)
                return {k: pick[k] for k in ("provider", "page", "author", "license")} | {"query": term}
        return None

    async def _contact_sheet(self, ctx, clips: list[str]) -> str:
        thumbs = []
        for rel in clips:
            frame = ctx.path(f"assets/raw/{rel.split('/')[-1]}.jpg")
            await ffmpeg.frame_at(ctx.run_dir / rel, frame, ctx.run_dir, at=1.0)
            thumbs.append(Image.open(frame).resize((216, 384)))
        cols = min(len(thumbs), 5)
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 216 + (cols + 1) * 8, rows * 384 + (rows + 1) * 8), (20, 20, 20))
        for n, t in enumerate(thumbs):
            sheet.paste(t, (8 + (n % cols) * 224, 8 + (n // cols) * 392))
        sheet.save(ctx.path("assets/contact_sheet.jpg"), quality=85)
        return "assets/contact_sheet.jpg"
