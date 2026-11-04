import asyncio
import colorsys
import random
import re
import zlib

from PIL import Image, ImageDraw, ImageFilter

from moderator.engine import llm as llm_mod
from moderator.engine.agent import Agent, StepContext
from moderator.tools import ffmpeg, stock, visual_rules

# Free stock video first; Nano Banana images (paid per image) only for scenes with no usable clip.
# visual_mode=ai puts Nano Banana first; visual_mode=stock never uses it.
TIERS = ["stock_video", "nano_banana", "stock_photo", "generated"]

FALLBACK_VIDEO_QUERIES = [
    "city street traffic",
    "clouds time lapse",
    "ocean waves",
    "man walking street",  # not "people": crowds tend to include women (see visual_rules)
    "night city lights",
    "rain falling",
    "train moving",
    "earth from space",
]


def _expand_queries(search_terms: list[str], scene_idx: int) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    primary: list[str] = []
    for raw in search_terms:
        q = visual_rules.safe_query(" ".join((raw or "").split()))
        if q and q.lower() not in seen:
            seen.add(q.lower())
            primary.append(q)
    for q in list(primary):
        words = [w for w in q.split() if len(w) > 2]
        if len(words) > 2:
            short = " ".join(words[:2])
            if short.lower() not in seen:
                seen.add(short.lower())
                primary.append(short)
    fallbacks: list[str] = []
    for offset in range(3):
        fb = FALLBACK_VIDEO_QUERIES[(scene_idx + offset) % len(FALLBACK_VIDEO_QUERIES)]
        if fb.lower() not in seen:
            seen.add(fb.lower())
            fallbacks.append(fb)
    return primary, fallbacks


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
        video_providers = [p for p in ("pexels", "pixabay", "wikimedia") if keys.get(p)]
        photo_providers = [p for p in ("pexels", "pixabay") if keys.get(p)]
        visual_mode = str(ctx.params.get("visual_mode") or "").lower()

        order = list(TIERS)
        if visual_mode in ("ai", "banana", "nano_banana"):
            order = ["nano_banana"] + [t for t in TIERS if t != "nano_banana"]
        elif visual_mode in ("stock", "video"):  # $0: never generate images
            order = [t for t in TIERS if t != "nano_banana"]
        start = order.index(ctx.strategy) if ctx.strategy in order else 0
        if visual_mode == "generated":
            start = order.index("generated")

        available_tiers = [
            t for t in order[start:]
            if (t == "generated")
            or (t == "nano_banana" and llm_mod.api_key_available())
            or (t == "stock_video" and video_providers)
            or (t == "stock_photo" and photo_providers)
        ]
        if not available_tiers:
            available_tiers = ["generated"]
        if available_tiers == ["generated"]:
            ctx.log("No GEMINI_API_KEY or stock video sources available: using procedural generated backgrounds", "warning")

        ctx.set_inputs(script=ctx.upstream("script")["data"], providers=video_providers,
                       nano_banana=llm_mod.api_key_available(), starting_tier=available_tiers[0])
        if ctx.feedback:
            ctx.log(f"Revision feedback: {ctx.feedback[-1]['comment']}")

        scenes = script["scenes"]
        used: set[str] = set()
        keep: dict[str, dict] = {}  # scene id -> license entry of a clip reused as is
        prev_lic_path = ctx.run_dir / "assets/licenses.json"
        if ctx.feedback and prev_lic_path.exists():
            previous = ctx.read_json("assets/licenses.json")
            used.update(item["page"] for item in previous if item.get("page"))
            # QA names the scenes it rejects (e.g. a woman in the shot): replace only those, keep the rest
            flagged = set(re.findall(r"scene_\d+", ctx.feedback[-1]["comment"]))
            if flagged:
                by_id = {s["id"]: s for s in scenes}
                for item in previous:
                    sc = by_id.get(item["scene"])
                    if (item["scene"] not in flagged and sc and item.get("description") == sc["visual"]["description"]
                            and (ctx.run_dir / f"assets/{item['scene']}.mp4").exists()):
                        keep[item["scene"]] = item
                ctx.log(f"Replacing {', '.join(sorted(flagged))}; keeping {len(keep)} unchanged scene(s)")
        pick_lock = asyncio.Lock()

        licenses: list[dict] = []
        sem = asyncio.Semaphore(3)
        done = 0

        async def produce(i: int, scene: dict) -> str:
            nonlocal done
            async with sem:
                out = ctx.path(f"assets/{scene['id']}.mp4")
                if scene["id"] in keep:
                    licenses.append(keep[scene["id"]])
                    done += 1
                    return out.relative_to(ctx.run_dir).as_posix()
                tiers = list(available_tiers)
                # Always keep moving stock_video ahead of static stock_photo unless explicitly requested via visual_mode=photo
                if visual_mode == "photo" and "stock_video" in tiers and "stock_photo" in tiers:
                    sv, sp = tiers.index("stock_video"), tiers.index("stock_photo")
                    if sv < sp:
                        tiers[sv], tiers[sp] = tiers[sp], tiers[sv]
                for tier in tiers:
                    try:
                        lic = await self._tier(
                            ctx, tier, scene, i, script["title"], video_providers, photo_providers, used, pick_lock, out
                        )
                    except Exception as e:  # noqa: BLE001 - fall through to the next tier
                        ctx.log(f"{scene['id']}: {tier} failed ({type(e).__name__}: {e})", "warning")
                        continue
                    if lic:
                        licenses.append({"scene": scene["id"], "tier": tier, **lic,
                                         "description": scene["visual"]["description"]})
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

    async def _tier(self, ctx, tier, scene, i, title, video_providers, photo_providers, used, pick_lock, out) -> dict | None:
        if tier == "nano_banana":
            png = ctx.path(f"assets/raw/{scene['id']}_banana.png")
            fb = f"\nRevision note: {ctx.feedback[-1]['comment']}" if ctx.feedback else ""
            prompt = (
                f"Vertical 9:16 cinematic visual for a faceless YouTube Short titled '{title}'. "
                f"Scene {i + 1}: {scene['visual']['description']}. "
                f"Style: {ctx.params.get('style', 'cinematic, moody lighting, clean composition')}. "
                "IMPORTANT: Do NOT render any text, letters, numbers, watermarks, brand logos, or recognizable celebrities. "
                f"Leave clean breathing room in the upper and lower thirds for burned-in captions. "
                f"{visual_rules.IMAGE_PROMPT_RULE}{fb}"
            )
            used_model = await ctx.llm.generate_image(prompt, png, aspect_ratio="9:16", size=(1080, 1920))
            await ffmpeg.still_to_clip(png, out, ctx.run_dir, seconds=10, zoom_in=i % 2 == 0)
            return {
                "provider": "nano_banana",
                "model": used_model,
                "query": scene["visual"]["description"],
                "license": f"AI-generated original image ({used_model}); no third-party rights",
            }
        if tier == "generated":
            png = ctx.path(f"assets/raw/{scene['id']}.png")
            seed = zlib.crc32(f"{ctx.store.data['run_id']}:{ctx.attempt}:{i}".encode())
            generated_background(png, seed=seed)
            await ffmpeg.still_to_clip(png, out, ctx.run_dir, seconds=10, zoom_in=i % 2 == 0)
            return {"provider": "generated", "license": "original work, no third-party rights"}

        primary_terms, fallback_terms = _expand_queries(scene["visual"]["search_terms"], i)
        if tier == "stock_video":
            hd_group = [p for p in ("pexels", "pixabay") if p in video_providers]
            zero_key_group = [p for p in ("wikimedia",) if p in video_providers]
            groups = [g for g in (hd_group, zero_key_group) if g]
            term_batches = [primary_terms, fallback_terms]
        else:
            groups = [photo_providers] if photo_providers else []
            term_batches = [primary_terms]

        for group in groups:
            for batch in term_batches:
                for term in batch:
                    for provider in group:
                        try:
                            results = (
                                await stock.search_videos(term, provider)
                                if tier == "stock_video"
                                else await stock.search_photos(term, provider)
                            )
                        except Exception as e:  # noqa: BLE001
                            ctx.log(f"{scene['id']}: {provider} search '{term}' failed ({e})", "warning")
                            continue

                        for attempt_idx in range(2):
                            async with pick_lock:
                                pick = next((r for r in results
                                             if r["page"] not in used and visual_rules.stock_allowed(r)), None)
                                if pick:
                                    used.add(pick["page"])
                            if not pick:
                                break
                            ext = pick.get("ext") or ("mp4" if tier == "stock_video" else "jpg")
                            raw = ctx.path(f"assets/raw/{scene['id']}_{attempt_idx}.{ext}")
                            try:
                                await stock.download(pick["url"], raw)
                                if tier == "stock_video":
                                    await ffmpeg.normalize_clip(raw, out, ctx.run_dir)
                                else:
                                    await ffmpeg.still_to_clip(raw, out, ctx.run_dir, seconds=10, zoom_in=i % 2 == 0)
                                return {k: pick[k] for k in ("provider", "page", "author", "license")} | {"query": term}
                            except Exception as e:  # noqa: BLE001
                                ctx.log(f"{scene['id']}: clip normalize failed for {pick['url']} ({e})", "warning")
                                continue
        return None

    async def _contact_sheet(self, ctx, clips: list[str]) -> str:
        thumbs = []
        for rel in clips:
            frame = ctx.path(f"assets/raw/{rel.split('/')[-1]}.jpg")
            await ffmpeg.frame_at(ctx.run_dir / rel, frame, ctx.run_dir, at=1.0)
            with Image.open(frame) as im:
                thumbs.append(im.resize((216, 384)))
        cols = min(len(thumbs), 5)
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 216 + (cols + 1) * 8, rows * 384 + (rows + 1) * 8), (20, 20, 20))
        for n, t in enumerate(thumbs):
            sheet.paste(t, (8 + (n % cols) * 224, 8 + (n // cols) * 392))
        sheet.save(ctx.path("assets/contact_sheet.jpg"), quality=85)
        return "assets/contact_sheet.jpg"
