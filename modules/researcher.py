"""
researcher.py — Topic research via DuckDuckGo + Crawl4AI.

Searches for trending news/insights on a given topic using DuckDuckGo,
then scrapes the top results using Crawl4AI (LLM-friendly markdown).
Returns cleaned text for the scriptwriter to synthesize.

Zero cost. No API key needed.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """Structured research output for the scriptwriter."""
    topic: str
    summaries: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)  # [{title, url, snippet}]
    raw_text: str = ""

    def to_context(self, max_chars: int = 8000) -> str:
        """Format research as LLM context string."""
        lines = [f"Topic: {self.topic}\n"]
        for i, src in enumerate(self.sources, 1):
            lines.append(f"Source {i}: {src.get('title', 'N/A')}")
            lines.append(f"URL: {src.get('url', 'N/A')}")
            lines.append(f"Search Snippet: {src.get('snippet', 'N/A')}\n")
            
            # If we successfully scraped the markdown for this URL, include it
            if src.get('markdown'):
                lines.append(f"--- Extracted Content ---\n{src['markdown'][:2500]}...\n--------------------------\n")
                
        context = "\n".join(lines)
        return context[:max_chars]


class Researcher:
    """Research engine using DuckDuckGo search + Crawl4AI web scraping."""

    def __init__(self):
        # Determine DDGS import path
        try:
            from ddgs import DDGS
            self.DDGS = DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
                self.DDGS = DDGS
            except ImportError:
                self.DDGS = None
                logger.error("DuckDuckGo search package not found. Run: pip install duckduckgo-search")


    def research(self, topic: str, max_results: int = 5) -> ResearchResult:
        """
        Synchronous wrapper around the async research pipeline.
        1. DuckDuckGo search for the topic
        2. Scrape top results for content via Crawl4AI
        3. Return structured ResearchResult
        """
        return asyncio.run(self._async_research(topic, max_results))


    async def _async_research(self, topic: str, max_results: int) -> ResearchResult:
        logger.info(f"🔍 Researching topic: {topic}")
        result = ResearchResult(topic=topic)

        # Step 1: Search
        search_results = self._search_ddg(topic, max_results=max_results)
        result.sources = search_results

        # Step 2: Scrape top results using Crawl4AI
        urls_to_scrape = [src.get("url") for src in search_results[:3] if src.get("url")]
        
        if urls_to_scrape:
            try:
                from crawl4ai import AsyncWebCrawler
                from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
                from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

                browser_config = BrowserConfig(headless=True)
                # Configure for fast text extraction only
                run_config = CrawlerRunConfig(
                    word_count_threshold=50,
                    markdown_generator=DefaultMarkdownGenerator()
                )

                logger.info(f"  🕷️ Crawling {len(urls_to_scrape)} top URLs with Crawl4AI...")
                
                async with AsyncWebCrawler(config=browser_config) as crawler:
                    # Run crawls concurrently
                    tasks = [crawler.arun(url=url, config=run_config) for url in urls_to_scrape]
                    crawl_results = await asyncio.gather(*tasks, return_exceptions=True)

                    for idx, crawl_res in enumerate(crawl_results):
                        src = result.sources[idx]
                        if isinstance(crawl_res, Exception):
                            logger.warning(f"  ⚠️ Failed to scrape {src['url'][:50]}: {crawl_res}")
                            continue
                            
                        if crawl_res.success:
                            markdown = crawl_res.markdown
                            src['markdown'] = markdown  # Save to the source dict directly
                            result.summaries.append(markdown)
                            logger.info(f"  📄 Scraped {len(markdown)} chars from {src['url'][:50]}...")
                        else:
                            logger.warning(f"  ⚠️ Crawl failed for {src['url'][:50]}: {crawl_res.error_message}")

            except ImportError:
                logger.error("Crawl4AI not installed. Run: pip install crawl4ai")

        # Build combined raw text
        result.raw_text = "\n\n".join(result.summaries)
        logger.info(f"✅ Research complete: {len(result.sources)} sources, "
                     f"{len(result.summaries)} scraped")
        return result

    def _search_ddg(self, query: str, max_results: int = 5) -> list[dict]:
        """Search DuckDuckGo and return structured results."""
        if not self.DDGS:
            return []
            
        try:
            results = []
            ddgs = self.DDGS()
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("url", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                })

            logger.info(f"  📋 DuckDuckGo: {len(results)} results for '{query}'")
            return results

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = Researcher()
    res = r.research("latest AI news February 2026")
    print(res.to_context())
