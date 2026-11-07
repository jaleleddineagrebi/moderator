"""Daily Internet Crawler for Psychology and Artificial Intelligence.

Fetches trending discussions and papers from:
1. arXiv API (cs.AI, cs.HC, stat.ML cross-checked with cognitive science/psychology keywords)
2. Open Scientific & Tech RSS feeds (MIT Tech Review, PsyPost, Nature Digital Medicine)
3. Reddit public JSON endpoints (r/psychology, r/artificial)
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from .llm_router import NativeOptimizer

logger = logging.getLogger("Crawler")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (PsychologyAIResearchBot/1.0; mailto:contact@moderator.internal)"
}


@dataclass
class RawArticle:
    title: str
    summary: str
    url: str
    source_name: str
    published_date: str
    keywords: list[str]


class ContentCrawler:
    def __init__(self):
        self.arxiv_url = "http://export.arxiv.org/api/query"
        self.rss_sources = [
            ("PsyPost AI", "https://www.psypost.org/category/artificial-intelligence/feed/"),
            ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
        ]
        self.reddit_subs = ["psychology", "artificial", "MachineLearning"]

    async def fetch_all(self, limit: int = 15) -> list[RawArticle]:
        """Gathers candidates from arXiv, RSS feeds, and Reddit in parallel."""
        tasks = [
            self.fetch_arxiv_papers(),
            self.fetch_rss_feeds(),
            self.fetch_reddit_discussions(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        candidates: list[RawArticle] = []
        for r in results:
            if isinstance(r, list):
                candidates.extend(r)
            elif isinstance(r, Exception):
                logger.error(f"Crawler error: {r}")

        # Native deduplication by URL and Title similarity ($0)
        seen_titles = set()
        unique: list[RawArticle] = []
        for art in candidates:
            norm_title = NativeOptimizer.slugify(art.title)
            if norm_title and norm_title not in seen_titles:
                seen_titles.add(norm_title)
                unique.append(art)

        logger.info(f"Crawled {len(unique)} unique articles across all sources")
        return unique[:limit]

    async def fetch_arxiv_papers(self) -> list[RawArticle]:
        """Queries arXiv for recent preprints merging AI and psychology."""
        query = 'all:"psychology" AND (cat:cs.AI OR cat:cs.HC OR cat:cs.CY)'
        params = {
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 10,
        }
        articles: list[RawArticle] = []
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
                res = await client.get(self.arxiv_url, params=params)
                if res.status_code != 200:
                    return articles
                
                root = ET.fromstring(res.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall("atom:entry", ns):
                    title = entry.find("atom:title", ns).text.strip() # type: ignore
                    summary = entry.find("atom:summary", ns).text.strip() # type: ignore
                    url = entry.find("atom:id", ns).text.strip() # type: ignore
                    published = entry.find("atom:published", ns).text.strip() # type: ignore

                    articles.append(RawArticle(
                        title=NativeOptimizer.clean_html_and_boilerplate(title),
                        summary=NativeOptimizer.clean_html_and_boilerplate(summary)[:600],
                        url=url,
                        source_name="arXiv API",
                        published_date=published,
                        keywords=NativeOptimizer.extract_keywords_heuristics(title, summary),
                    ))
        except Exception as e:
            logger.warning(f"Failed to fetch arXiv papers: {e}")
        return articles

    async def fetch_rss_feeds(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            for name, feed_url in self.rss_sources:
                try:
                    res = await client.get(feed_url)
                    if res.status_code == 200:
                        root = ET.fromstring(res.content)
                        for item in root.findall(".//item")[:5]:
                            title = item.find("title").text if item.find("title") is not None else "" # type: ignore
                            link = item.find("link").text if item.find("link") is not None else "" # type: ignore
                            desc = item.find("description").text if item.find("description") is not None else "" # type: ignore
                            
                            # Filter for relevance with Psychology & AI
                            comb = f"{title} {desc}".lower()
                            if ("ai" in comb or "algorithm" in comb or "neural" in comb) and ("psycholog" in comb or "brain" in comb or "bias" in comb or "cognit" in comb):
                                articles.append(RawArticle(
                                    title=NativeOptimizer.clean_html_and_boilerplate(title),
                                    summary=NativeOptimizer.clean_html_and_boilerplate(desc)[:400],
                                    url=link,
                                    source_name=name,
                                    published_date=datetime.now(timezone.utc).isoformat(),
                                    keywords=NativeOptimizer.extract_keywords_heuristics(title, desc),
                                ))
                except Exception as e:
                    logger.warning(f"Failed RSS feed {name}: {e}")
        return articles

    async def fetch_reddit_discussions(self) -> list[RawArticle]:
        articles: list[RawArticle] = []
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            for sub in self.reddit_subs:
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=15"
                try:
                    res = await client.get(url)
                    if res.status_code == 200:
                        data = res.json()
                        posts = data.get("data", {}).get("children", [])
                        for p in posts:
                            d = p.get("data", {})
                            title = d.get("title", "")
                            selftext = d.get("selftext", "")
                            permalink = f"https://reddit.com{d.get('permalink', '')}"
                            
                            comb = f"{title} {selftext}".lower()
                            if ("ai" in comb or "gpt" in comb or "machine learning" in comb) and ("mind" in comb or "mental" in comb or "bias" in comb or "behavio" in comb):
                                articles.append(RawArticle(
                                    title=title,
                                    summary=NativeOptimizer.clean_html_and_boilerplate(selftext)[:400],
                                    url=permalink,
                                    source_name=f"Reddit r/{sub}",
                                    published_date=datetime.now(timezone.utc).isoformat(),
                                    keywords=NativeOptimizer.extract_keywords_heuristics(title, selftext),
                                ))
                except Exception as e:
                    logger.warning(f"Reddit r/{sub} fetch failed: {e}")
        return articles
