"""
researcher.py — Topic research via DuckDuckGo + web scraping.

Searches for trending news/insights on a given topic, scrapes top results,
and returns cleaned text for the scriptwriter to synthesize.

Zero cost. No API key needed.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """Structured research output for the scriptwriter."""
    topic: str
    summaries: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)  # [{title, url, snippet}]
    raw_text: str = ""

    def to_context(self, max_chars: int = 4000) -> str:
        """Format research as LLM context string."""
        lines = [f"Topic: {self.topic}\n"]
        for i, src in enumerate(self.sources, 1):
            lines.append(f"Source {i}: {src.get('title', 'N/A')}")
            lines.append(f"URL: {src.get('url', 'N/A')}")
            lines.append(f"Summary: {src.get('snippet', 'N/A')}\n")
        context = "\n".join(lines)
        return context[:max_chars]


class Researcher:
    """Research engine using DuckDuckGo search + web scraping."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })

    def research(self, topic: str, max_results: int = 5) -> ResearchResult:
        """
        Full research pipeline:
        1. DuckDuckGo search for the topic
        2. Scrape top results for content
        3. Return structured ResearchResult
        """
        logger.info(f"🔍 Researching topic: {topic}")
        result = ResearchResult(topic=topic)

        # Step 1: Search
        search_results = self._search_ddg(topic, max_results=max_results)
        result.sources = search_results

        # Step 2: Scrape top results for deeper content
        for source in search_results[:3]:  # Scrape top 3 only
            url = source.get("url", "")
            if url:
                scraped = self._scrape_page(url)
                if scraped:
                    result.summaries.append(scraped[:1000])  # Limit per source

        # Build combined raw text
        result.raw_text = "\n\n".join(result.summaries)
        logger.info(f"✅ Research complete: {len(result.sources)} sources, "
                     f"{len(result.summaries)} scraped")
        return result

    def _search_ddg(self, query: str, max_results: int = 5) -> list[dict]:
        """Search DuckDuckGo and return structured results."""
        try:
            # New package name (renamed from duckduckgo_search → ddgs)
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            results = []
            ddgs = DDGS()
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("url", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                })

            logger.info(f"  📋 DuckDuckGo: {len(results)} results for '{query}'")
            return results

        except ImportError:
            logger.error("ddgs not installed. Run: pip install ddgs")
            return []
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []

    def _scrape_page(self, url: str, timeout: int = 10) -> Optional[str]:
        """Scrape a web page and extract clean text content."""
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove non-content elements
            for tag in soup(["script", "style", "nav", "footer", "header",
                             "aside", "iframe", "noscript", "form"]):
                tag.decompose()

            # Extract text
            text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r" {2,}", " ", text)

            # Skip very short pages (likely paywalls/errors)
            if len(text) < 100:
                return None

            logger.info(f"  📄 Scraped {len(text)} chars from {url[:50]}...")
            return text

        except Exception as e:
            logger.warning(f"  ⚠️ Failed to scrape {url[:50]}: {e}")
            return None


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = Researcher()
    result = r.research("latest AI news February 2026")
    print(result.to_context())
