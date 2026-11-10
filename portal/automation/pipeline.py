"""AI-Powered Content Generation Pipeline for Daily Psychology & AI Posts.

Generates high-impact, scientifically framed articles directly using AI and Python
without any web scraping or crawling dependencies.

Produces two focused daily publications:
- Morning Focus: Cognitive biases & human behavior in the AI era.
- Evening Insight: Mental models, neuroscience & human-machine teaming frameworks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .image_service import ImageService
from .llm_router import CostOptimizedLLMRouter, NativeOptimizer
from .storage_service import StorageService
from .youtube_shorts import fetch_channel_shorts, is_youtube_id, pick_unused

logger = logging.getLogger("Pipeline")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TOPICS_HISTORY_PATH = PROJECT_ROOT / "history" / "topics.jsonl"
DAILY_POSTS_DIR = PROJECT_ROOT / "history" / "daily_posts"

CORE_PILLARS = [
    "Cognitive Offloading & Neural Synaptic Atrophy in Generative AI",
    "Automation Bias & Prefrontal Cortex Glucose Conservation",
    "The Illusion of Competence & Synthetic Fluency",
    "Dopamine Loops & Algorithmic Variable Reward Schedules",
    "Working Memory Bottlenecks in Prompt Engineering",
    "The Extended Mind Thesis & Cognitive Ergonomics of LLMs",
    "Hyperbolic Discounting & Long-Term Skill Retention",
    "Epistemic Vigilance & Hallucination Acceptance Psychology",
    "The Spotlight Effect & Social Anxiety in Remote Digital Teaming",
    "Mental Models: Inversion & First Principles in Human-AI Problem Solving",
]


class DailyContentPipeline:
    def __init__(self):
        self.router = CostOptimizedLLMRouter()
        self.images = ImageService()
        self.storage = StorageService()

    def get_used_short_ids(self) -> set[str]:
        """YouTube video IDs already attached to an earlier article (each Short is used once)."""
        used: set[str] = set()
        if DAILY_POSTS_DIR.exists():
            for p in DAILY_POSTS_DIR.glob("*.json"):
                try:
                    for item in json.loads(p.read_text(encoding="utf-8")):
                        if isinstance(item, dict) and is_youtube_id(item.get("youtubeShortId")):
                            used.add(item["youtubeShortId"])
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Could not read {p.name}: {e}")
        return used

    async def get_existing_video_cross_references(self) -> list[dict[str, Any]]:
        """Real public Shorts of the channel that no article has used yet, newest first."""
        shorts = await fetch_channel_shorts()
        unused = pick_unused(shorts, self.get_used_short_ids(), count=2)
        for s in unused:
            s["angle"] = s.get("hookAngle") or ""
        return unused

    def get_recent_post_topics(self) -> list[str]:
        """Loads topics covered in recent daily post archives to prevent repetition."""
        if not DAILY_POSTS_DIR.exists():
            return []
        recent_titles: list[str] = []
        try:
            for p in sorted(DAILY_POSTS_DIR.glob("*.json"), reverse=True)[:14]:
                items = json.loads(p.read_text(encoding="utf-8"))
                for it in items:
                    if isinstance(it, dict) and "title" in it:
                        recent_titles.append(it["title"])
        except Exception as e:
            logger.warning(f"Could not read recent daily post history: {e}")
        return recent_titles

    def get_recent_cover_images(self) -> set[str]:
        """Loads coverImageUrl values used in recent daily post archives so no two posts repeat the same image."""
        if not DAILY_POSTS_DIR.exists():
            return set()
        used_urls: set[str] = set()
        try:
            for p in sorted(DAILY_POSTS_DIR.glob("*.json"), reverse=True)[:30]:
                items = json.loads(p.read_text(encoding="utf-8"))
                for it in items:
                    if isinstance(it, dict) and it.get("coverImageUrl"):
                        used_urls.add(str(it["coverImageUrl"]))
        except Exception as e:
            logger.warning(f"Could not read recent cover image history: {e}")
        return used_urls

    async def generate_post(
        self,
        slot: str,
        matched_short: dict[str, Any] | None,
        recent_titles: list[str],
        used_images: set[str] | None = None,
    ) -> dict[str, Any]:
        """Generates an original, high-quality Psychology & AI publication using AI directly."""
        logger.info(f"Generating [{slot}] publication via AI...")

        avoid_clause = ""
        if recent_titles:
            avoid_list = "\n- ".join(recent_titles[:10])
            avoid_clause = f"\nTopics already covered recently (DO NOT repeat these):\n- {avoid_list}\n"

        short_context = ""
        if matched_short:
            short_context = (
                f"\nCompanion YouTube Short context:\n"
                f"- Title: {matched_short.get('title')}\n"
                f"- Angle/Hook: {matched_short.get('angle')}\n"
                f"(You may expand and provide deep cognitive analysis on this theme or related psychological principles.)\n"
            )

        prompt = f"""You are a cognitive psychologist and neuroscientist researching human-AI interaction.
Write an engaging, scientifically rigorous article for an intellectual audience exploring the intersection of psychology, cognitive biases, and artificial intelligence.

Slot: {slot.upper()}
{avoid_clause}
{short_context}

REQUIREMENTS:
1. 'title': Max 60 characters, curiosity-driven, no clickbait hype.
2. 'concept': Primary psychological or cognitive phenomenon explored (e.g. 'Cognitive Offloading', 'Automation Bias', 'Working Memory Load').
3. 'hook': 1-2 punchy sentences that interrupt the reader's autopilot ("Why your brain...", "You assume AI does X, but neuroscience shows Y").
4. 'summary': 2-3 sentence clear takeaway explaining the mental mechanism.
5. 'contentMarkdown': 350-500 words in GitHub Markdown format with these exact four sections:
   - ## The Psychological Paradox
   - ## What the Science Shows
   - ## Daily Brain Bias Check (actionable self-reflection prompt for readers)
   - ## Practical Takeaway
6. 'tags': Array of 3-5 concise tags (e.g. ["Cognitive Bias", "Human-AI Teaming", "Neuroscience", "Mental Models"]).
7. 'imageSearchQuery': 2-3 specific, concrete photography words matching THIS article's unique metaphor (e.g. "chess clock strategy", "labyrinth neon corridor", "prism light refraction", "hourglass sand macro" — NEVER generic "brain abstract" or "AI").

Format strictly as JSON with keys: 'title', 'concept', 'hook', 'summary', 'contentMarkdown', 'tags', 'imageSearchQuery'."""

        synth_res = await self.router.route_and_generate(
            prompt=prompt,
            complexity="low",  # the router always uses the cheapest model
            json_output=True,
        )

        post_data = NativeOptimizer.safe_json_extract(synth_res.content)
        title = post_data.get("title", f"Psychological Insights in AI ({slot})")
        concept = post_data.get("concept", "Cognitive Science & AI")
        hook = post_data.get("hook", "How artificial intelligence alters human cognitive habits.")
        summary = post_data.get("summary", "A psychological breakdown of human-AI behavior.")
        content = post_data.get("contentMarkdown", "## The Psychological Paradox\nInsights into human cognition.")
        tags = post_data.get("tags", ["Psychology", "Artificial Intelligence", "Cognitive Science"])
        img_query = post_data.get("imageSearchQuery", concept)

        # Pure Python Slugification ($0)
        date_str = datetime.now(timezone.utc).strftime("%m%d")
        slug = f"{NativeOptimizer.slugify(title)}-{date_str}"

        # Visual Sourcing & Cloud Storage Persistence (with deduplication across recent posts)
        active_used = used_images if used_images is not None else getattr(self, "_used_images", None)
        if active_used is None:
            active_used = self.get_recent_cover_images()
            self._used_images = active_used
        img = await self.images.get_image_for_post(img_query, exclude_urls=active_used, seed_key=slug)
        active_used.add(img.image_url)
        permanent_image_url = await self.storage.persist_image_from_url(img.image_url, slug)

        return {
            "slug": slug,
            "title": title,
            "hook": hook,
            "summary": summary,
            "contentMarkdown": content,
            "coverImageUrl": permanent_image_url,
            "imageCredit": img.credit,
            "tags": tags,
            "sourceUrls": ["https://arxiv.org", "https://nature.com/neuro"],
            "aiModelUsed": synth_res.model_used,
            "synthesisCostUsd": round(synth_res.estimated_cost_usd, 6),
            "youtubeShortId": matched_short["id"] if matched_short else None,
            "youtubeShort": matched_short,  # the API creates this row first, so the post can reference it
            "status": "PUBLISHED",
            "publishedAt": datetime.now(timezone.utc).isoformat(),
        }

    async def run_daily(self) -> list[dict[str, Any]]:
        """Main execution loop that generates 2 daily AI-synthesized publications."""
        logger.info("Starting AI-Powered Daily Content Generation (No Crawling)...")

        existing_shorts = await self.get_existing_video_cross_references()
        recent_titles = self.get_recent_post_topics()
        self._used_images = self.get_recent_cover_images()

        short1 = existing_shorts[0] if len(existing_shorts) > 0 else None
        short2 = existing_shorts[1] if len(existing_shorts) > 1 else None

        morning_post = await self.generate_post("Morning Focus", short1, recent_titles)
        recent_titles.append(morning_post["title"])

        evening_post = await self.generate_post("Evening Insight", short2, recent_titles)

        posts = [morning_post, evening_post]

        # Archive first (one file per run; the PR and the dedupe history use it), then push to the database
        DAILY_POSTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
        save_path = DAILY_POSTS_DIR / f"{stamp}.json"
        save_path.write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Saved {len(posts)} daily posts to {save_path}")
        self._write_github_outputs(save_path, posts)

        api_endpoint = os.getenv("PORTAL_API_ENDPOINT", "").strip()
        api_secret = os.getenv("INTERNAL_API_SECRET", "").strip()
        if not (api_endpoint and api_secret):
            raise RuntimeError(
                "PORTAL_API_ENDPOINT and INTERNAL_API_SECRET are not set: the posts were generated and archived "
                "but NOT saved to the database. Add both GitHub secrets (docs/SETUP.md)."
            )
        results = await self._push_to_web_portal(api_endpoint, api_secret, posts)
        self._write_step_summary(posts, results)
        failed = [r for r in results if not r["ok"]]
        if failed:
            raise RuntimeError("Posts NOT saved to the database: " + "; ".join(f"{r['slug']}: {r['detail']}" for r in failed))
        return posts

    @staticmethod
    def _write_github_outputs(save_path: Path, posts: list[dict[str, Any]]) -> None:
        if out := os.getenv("GITHUB_OUTPUT"):
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"posts_file={save_path.relative_to(PROJECT_ROOT).as_posix()}\n")
                f.write(f"posts_titles={' | '.join(p['title'] for p in posts)}\n")

    @staticmethod
    def _write_step_summary(posts: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
        if not (path := os.getenv("GITHUB_STEP_SUMMARY")):
            return
        by_slug = {r["slug"]: r for r in results}
        lines = ["### Daily posts", "", "| Post | Companion Short | Database |", "| :--- | :--- | :--- |"]
        for p in posts:
            r = by_slug.get(p["slug"], {"ok": False, "detail": "not pushed"})
            short = f"https://www.youtube.com/shorts/{p['youtubeShortId']}" if p.get("youtubeShortId") else "none"
            lines.append(f"| {p['title']} | {short} | {'saved' if r['ok'] else 'FAILED: ' + str(r['detail'])} |")
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    async def _push_to_web_portal(self, endpoint: str, secret: str, posts: list[dict]) -> list[dict[str, Any]]:
        """POST every post to the portal API (which upserts it in the database)."""
        import httpx
        url = f"{endpoint.rstrip('/')}/api/posts"
        headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            return [await self._post_one(client, url, headers, p) for p in posts]

    @staticmethod
    async def _post_one(client, url: str, headers: dict, post: dict) -> dict[str, Any]:
        """One post, with a single retry on 5xx or network errors (4xx means the request itself is wrong)."""
        import httpx
        detail = ""
        for attempt in (1, 2):
            retryable = True
            try:
                res = await client.post(url, headers=headers, json=post)
                if res.status_code in (200, 201):
                    logger.info(f"Saved to the database: {post['slug']} (HTTP {res.status_code})")
                    return {"slug": post["slug"], "ok": True, "detail": f"HTTP {res.status_code}"}
                detail = f"HTTP {res.status_code}: {res.text[:300]}"
                retryable = res.status_code >= 500
            except httpx.HTTPError as e:
                detail = f"{type(e).__name__}: {e}"
            if attempt == 1 and retryable:
                await asyncio.sleep(3)
            else:
                break
        logger.error(f"Could not save {post['slug']} to the database: {detail}")
        return {"slug": post["slug"], "ok": False, "detail": detail}


if __name__ == "__main__":
    asyncio.run(DailyContentPipeline().run_daily())
