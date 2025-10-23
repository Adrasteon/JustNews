from common.observability import get_logger

#!/usr/bin/env python3
"""Generic multi-site crawler with Crawl4AI-first strategy.

This module provides:
- SiteConfig: per-site selector configuration
- GenericSiteCrawler: article discovery + extraction for a single site
- MultiSiteCrawler: orchestration across multiple sites concurrently

Strategy:
1. Prefer Crawl4AI for link discovery & article extraction (fast, cleaner text)
2. Gracefully fall back to Playwright when Crawl4AI fails or disabled
3. Emit canonical metadata objects expected by downstream agents
"""

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
from typing import Any, List
from urllib.parse import urljoin, urlparse

try:  # pragma: no cover
    from crawl4ai import AsyncWebCrawler  # type: ignore
    _CRAWL4AI_AVAILABLE = True
except Exception:  # noqa: BLE001
    _CRAWL4AI_AVAILABLE = False

from playwright.async_api import async_playwright

from ...tools import _record_scout_performance
from ..crawler_utils import (
    CanonicalMetadata,
    ModalDismisser,
    RateLimiter,
    RobotsChecker,
    get_active_sources,
    get_sources_by_domain,
)

logger = get_logger(__name__)


class SiteConfig:
    """Configuration for a specific news site."""

    def __init__(self, source_data: dict[str, Any]):
        self.source_id = source_data.get("id")
        self.url = source_data.get("url")
        self.domain = source_data.get("domain")
        self.name = source_data.get("name", "Unknown")
        self.description = source_data.get("description", "")
        self.metadata = source_data.get("metadata", {})

        # Default selectors (override via metadata["selectors"])
        self.article_link_selectors = [
            "a[href*='article']",
            "a[href*='news']",
            "a[href*='story']",
            "a[href*='/202']",  # Date patterns
            ".headline a",
            ".story-link",
            "[data-testid*='article'] a",
        ]
        self.title_selectors = [
            "h1",
            "[data-component='headline']",
            ".story-headline",
            ".article-title",
            "[role='main'] h1",
        ]
        self.content_selectors = [
            "[data-component='text-block']",
            ".story-body__inner",
            "[role='main'] p",
            "main p",
            ".article-body p",
            "[data-testid='paragraph']",
            ".content p",
        ]

        if "selectors" in self.metadata:
            selectors = self.metadata["selectors"]
            self.article_link_selectors = selectors.get(
                "article_links", self.article_link_selectors
            )
            self.title_selectors = selectors.get("title", self.title_selectors)
            self.content_selectors = selectors.get("content", self.content_selectors)

    def get_base_url(self) -> str:
        parsed = urlparse(self.url)
        return f"{parsed.scheme}://{parsed.netloc}"


class GenericSiteCrawler:
    """Crawler for a single site (Crawl4AI preferred, Playwright fallback)."""

    def __init__(
        self,
        site_config: SiteConfig,
        concurrent_browsers: int = 2,
        batch_size: int = 8,
    ):
        self.site_config = site_config
        self.concurrent_browsers = concurrent_browsers
        self.batch_size = batch_size
        self.rate_limiter = RateLimiter()
        self.robots_checker = RobotsChecker()
        self.processed_urls: set[str] = set()
        self.session_start_time = time.time()

    async def get_article_urls(self, max_urls: int = 40) -> list[str]:
        """Discover candidate article URLs.

        Order of attempts:
        1. Crawl4AI (if available & not forced Playwright)
        2. Playwright DOM discovery
        """
        use_crawl4ai = (
            _CRAWL4AI_AVAILABLE
            and os.environ.get("GENERIC_CRAWLER_USE_PLAYWRIGHT", "0") != "1"
        )
        urls: list[str] = []
        base = self.site_config.get_base_url()

        if use_crawl4ai:
            try:  # pragma: no cover - network
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await crawler.arun(url=self.site_config.url)
                html = getattr(result, "raw_html", None) or getattr(
                    result, "cleaned_html", ""
                )
                for match in re.findall(r'href=["\']([^"\']+)["\']', html):
                    href = match.strip()
                    if href.startswith("/"):
                        href = urljoin(base, href)
                    if not href.startswith("http"):
                        continue
                    if any(
                        key in href.lower()
                        for key in [
                            "video",
                            "live",
                            "audio",
                            "sport",
                            "gallery",
                            "podcast",
                        ]
                    ):
                        continue
                    if re.search(r"/[0-9]{4}/[0-9]{2}/[0-9]{2}/", href) or any(
                        token in href.lower() for token in ["article", "story", "news"]
                    ):
                        urls.append(href.split("#")[0])
                    if len(urls) >= max_urls:
                        break
                urls = list(dict.fromkeys(urls))  # de-dupe, preserve order
                if urls:
                    logger.info(
                        f"✅ [Crawl4AI] Found {len(urls)} URLs for {self.site_config.name}"
                    )
                    return urls[:max_urls]
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    f"Crawl4AI link discovery failed for {self.site_config.name}: {e}"  # noqa: E501
                )

        # Fallback: Playwright DOM evaluation
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await page.goto(self.site_config.url, timeout=15000)
            await ModalDismisser.dismiss_modals(page)
            await asyncio.sleep(1.0)
            anchors = await page.locator("a").element_handles()
            for a in anchors:
                try:
                    href = await a.get_attribute("href")
                    if not href:
                        continue
                    if href.startswith("/"):
                        href = urljoin(base, href)
                    if not href.startswith("http"):
                        continue
                    if any(
                        skip in href.lower()
                        for skip in [
                            "video",
                            "live",
                            "audio",
                            "sport",
                            "gallery",
                            "podcast",
                        ]
                    ):
                        continue
                    if re.search(r"/[0-9]{4}/[0-9]{2}/[0-9]{2}/", href) or any(
                        token in href.lower() for token in ["article", "story", "news"]
                    ):
                        urls.append(href.split("#")[0])
                    if len(urls) >= max_urls:
                        break
                except Exception:  # noqa: BLE001
                    continue
            urls = list(dict.fromkeys(urls))
            logger.info(
                f"✅ [Playwright] Found {len(urls)} article URLs from {self.site_config.name}"  # noqa: E501
            )
            return urls[:max_urls]
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"❌ Failed to get URLs from {self.site_config.name}: {e}"  # noqa: E501
            )
            return []
        finally:
            try:
                await browser.close()
                await playwright.stop()
            except Exception:  # noqa: BLE001
                pass

    async def extract_content(self, page) -> dict[str, Any]:
        """Extract article title + content via configured selectors."""
        try:
            title = ""
            for selector in self.site_config.title_selectors:
                try:
                    element = page.locator(selector).first
                    title_candidate = await element.text_content()
                    if title_candidate and len(title_candidate.strip()) > 10:
                        title = title_candidate.strip()
                        break
                except Exception:  # noqa: BLE001
                    continue

            content_parts: list[str] = []
            for selector in self.site_config.content_selectors:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    for i in range(min(count, 8)):
                        try:
                            text = await elements.nth(i).text_content()
                            if text and len(text.strip()) > 20:
                                content_parts.append(text.strip())
                        except Exception:  # noqa: BLE001
                            continue
                    if len(content_parts) > 3:
                        break
                except Exception:  # noqa: BLE001
                    continue

            content = " ".join(content_parts)
            canonical, paywall_flag = await CanonicalMetadata.extract_canonical_and_paywall(page)  # noqa: E501
            return {
                "title": title,
                "content": content,
                "canonical": canonical,
                "paywall_flag": paywall_flag,
                "extraction_method": "generic_dom",
                "extraction_metadata": {
                    "site_config": self.site_config.name,
                    "content_length": len(content),
                    "paragraphs_found": len(content_parts),
                },
            }
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Content extraction failed: {e}")
            return {
                "title": "Error",
                "content": f"Extraction failed: {e}",
                "canonical": None,
                "paywall_flag": False,
                "extraction_method": "error",
                "extraction_metadata": {"error": str(e)},
            }

    async def process_single_url(self, browser, url: str) -> dict | None:
        if url in self.processed_urls:
            return None
        self.processed_urls.add(url)
        start_time = time.time()
        try:
            if not self.robots_checker.check_robots_txt(url):
                logger.info(f"⚠️ Robots.txt disallows crawling: {url}")
                processing_time = time.time() - start_time
                _record_scout_performance({
                    "agent_name": "scout",
                    "operation": "process_single_url",
                    "processing_time_s": processing_time,
                    "batch_size": 1,
                    "success": False,
                    "throughput_items_per_s": 1 / processing_time if processing_time > 0 else 0,
                })
                return CanonicalMetadata.generate_metadata(
                    url=url,
                    title="Robots.txt Disallowed",
                    content="Crawling not allowed by robots.txt",
                    extraction_method="disallowed",
                    status="disallowed",
                    paywall_flag=False,
                    confidence=0.0,
                    publisher=self.site_config.name,
                    crawl_mode="generic_site",
                    news_score=0.0,
                )
            await self.rate_limiter.wait_if_needed(self.site_config.domain)
            use_crawl4ai = (
                _CRAWL4AI_AVAILABLE
                and os.environ.get("GENERIC_CRAWLER_USE_PLAYWRIGHT", "0") != "1"
            )
            if use_crawl4ai:
                try:
                    async with AsyncWebCrawler(verbose=False) as crawler:
                        result = await crawler.arun(
                            url=url,
                            extraction_strategy="LLMExtractionStrategy",
                            css_selector="main, article, .content, .story-body, [role='main']",  # noqa: E501
                            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                        )
                        content = (
                            result.cleaned_html
                            or result.markdown
                            or result.extracted_content
                            or ""
                        )
                        clean_text = re.sub(r"<[^>]+>", " ", content)
                        clean_text = re.sub(r"\s+", " ", clean_text).strip()
                        title = getattr(result, "title", "") or (
                            self.site_config.name + " Article"
                        )
                        if len(clean_text) > 80 and len(title) > 5:
                            processing_time = time.time() - start_time
                            _record_scout_performance({
                                "agent_name": "scout",
                                "operation": "process_single_url",
                                "processing_time_s": processing_time,
                                "batch_size": 1,
                                "success": True,
                                "throughput_items_per_s": 1 / processing_time if processing_time > 0 else 0,
                            })
                            return CanonicalMetadata.generate_metadata(
                                url=url,
                                title=title[:300],
                                content=clean_text[:12000],
                                extraction_method="crawl4ai_generic",
                                status="success",
                                paywall_flag=False,
                                confidence=0.72,
                                publisher=self.site_config.name,
                                crawl_mode="generic_site",
                                news_score=0.72,
                                canonical=None,
                            )
                except Exception as e:  # noqa: BLE001
                    logger.debug(
                        f"Crawl4AI extraction failed for {url}: {e} – falling back to Playwright"  # noqa: E501
                    )
            # Fallback: Playwright
            context = await browser.new_context(
                viewport={"width": 1024, "height": 768},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            await ModalDismisser.dismiss_modals(page)
            await asyncio.sleep(1.5)
            content_data = await self.extract_content(page)
            await context.close()
            await asyncio.sleep(random.uniform(1.0, 3.0))
            if (
                len(content_data["content"]) > 50
                and len(content_data["title"]) > 10
            ):
                processing_time = time.time() - start_time
                _record_scout_performance({
                    "agent_name": "scout",
                    "operation": "process_single_url",
                    "processing_time_s": processing_time,
                    "batch_size": 1,
                    "success": True,
                    "throughput_items_per_s": 1 / processing_time if processing_time > 0 else 0,
                })
                return CanonicalMetadata.generate_metadata(
                    url=url,
                    title=content_data["title"],
                    content=content_data["content"],
                    extraction_method=content_data["extraction_method"],
                    status="success",
                    paywall_flag=content_data["paywall_flag"],
                    confidence=0.7,
                    publisher=self.site_config.name,
                    crawl_mode="generic_site",
                    news_score=0.7,
                    canonical=content_data["canonical"],
                )
            processing_time = time.time() - start_time
            _record_scout_performance({
                "agent_name": "scout",
                "operation": "process_single_url",
                "processing_time_s": processing_time,
                "batch_size": 1,
                "success": False,
                "throughput_items_per_s": 1 / processing_time if processing_time > 0 else 0,
            })
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to process {url}: {e}")
            processing_time = time.time() - start_time
            _record_scout_performance({
                "agent_name": "scout",
                "operation": "process_single_url",
                "processing_time_s": processing_time,
                "batch_size": 1,
                "success": False,
                "throughput_items_per_s": 1 / processing_time if processing_time > 0 else 0,
            })
            return CanonicalMetadata.generate_metadata(
                url=url,
                title="Error",
                content=f"Processing failed: {e}",
                extraction_method="error",
                status="error",
                paywall_flag=False,
                confidence=0.0,
                publisher=self.site_config.name,
                crawl_mode="generic_site",
                news_score=0.0,
                error=str(e),
            )

    async def crawl_site(self, max_articles: int = 25) -> list[dict]:
        logger.info(
            f"🚀 Starting generic crawl of {self.site_config.name} for {max_articles} articles"
        )
        urls = await self.get_article_urls(max_urls=max_articles * 2)
        if not urls:
            logger.warning(f"❌ No URLs found for {self.site_config.name}")
            return []
        playwright = await async_playwright().start()
        browsers = []
        try:
            for _ in range(self.concurrent_browsers):
                browsers.append(await playwright.chromium.launch(headless=True))
            results: list[dict] = []
            browser_index = 0
            for i in range(0, len(urls), self.batch_size):
                batch = urls[i : i + self.batch_size]
                logger.info(
                    f"📦 Processing batch {i // self.batch_size + 1}: {len(batch)} URLs"
                )
                tasks = []
                for u in batch:
                    b = browsers[browser_index % len(browsers)]
                    browser_index += 1
                    tasks.append(self.process_single_url(b, u))
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in batch_results:
                    if isinstance(r, dict) and r.get("status") == "success":
                        results.append(r)
                        logger.info(f"✅ Success: {r['title'][:50]}...")
                await asyncio.sleep(0.4)
            elapsed = time.time() - self.session_start_time
            rate = len(results) / elapsed if elapsed else 0.0
            logger.info(
                f"🎉 Generic site crawl complete: {len(results)} articles (rate {rate:.2f}/s)"  # noqa: E501
            )
            return results
        finally:
            for b in browsers:
                try:
                    await b.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                await playwright.stop()
            except Exception:  # noqa: BLE001
                pass


class MultiSiteCrawler:
    """Coordinates crawling across multiple sites"""

    def __init__(self, concurrent_sites: int = 3, articles_per_site: int = 25):
        self.concurrent_sites = concurrent_sites
        self.articles_per_site = articles_per_site
        self.site_crawlers = {}

    async def load_sources_from_db(self, domains: list[str] = None) -> list[SiteConfig]:
        """Load site configurations from database"""
        if domains:
            sources = get_sources_by_domain(domains)
        else:
            sources = get_active_sources()

        site_configs = []
        for source in sources:
            try:
                config = SiteConfig(source)
                site_configs.append(config)
                logger.info(f"📋 Loaded config for {config.name} ({config.domain})")
            except Exception as e:
                logger.warning(f"Failed to create config for {source.get('name', 'Unknown')}: {e}")

        logger.info(f"✅ Loaded {len(site_configs)} site configurations")
        return site_configs

    async def crawl_multiple_sites(self, site_configs: list[SiteConfig],
                                 max_total_articles: int = 100) -> dict[str, list[dict]]:
        """Crawl multiple sites concurrently"""
        logger.info(f"🚀 Starting multi-site crawl of {len(site_configs)} sites")

        results = {}
        semaphore = asyncio.Semaphore(self.concurrent_sites)

        async def crawl_site_with_limit(site_config: SiteConfig):
            async with semaphore:
                crawler = GenericSiteCrawler(site_config)
                articles = await crawler.crawl_site(self.articles_per_site)
                results[site_config.domain] = articles
                logger.info(f"🏁 Completed {site_config.name}: {len(articles)} articles")

        # Create tasks for all sites
        tasks = [crawl_site_with_limit(config) for config in site_configs]

        # Execute concurrently with site limit
        await asyncio.gather(*tasks, return_exceptions=True)

        # Summarize results
        total_articles = sum(len(articles) for articles in results.values())
        logger.info("🎉 Multi-site crawl complete!")
        logger.info(f"📊 Total articles: {total_articles}")
        logger.info(f"📈 Sites crawled: {len(results)}")

        return results

    async def run_multi_site_crawl(self, domains: list[str] = None,
                                 max_total_articles: int = 100) -> dict[str, Any]:
        """Main entry point for multi-site crawling"""
        start_time = time.time()

        # Load site configurations
        site_configs = await self.load_sources_from_db(domains)
        if not site_configs:
            logger.error("❌ No site configurations loaded")
            return {"error": "No sites available"}

        # Crawl all sites
        site_results = await self.crawl_multiple_sites(site_configs, max_total_articles)

        # Flatten results for easier processing
        all_articles = []
        for domain, articles in site_results.items():
            all_articles.extend(articles)

        processing_time = time.time() - start_time
        articles_per_second = len(all_articles) / processing_time if processing_time > 0 else 0

        summary = {
            "multi_site_crawl": True,
            "sites_crawled": len(site_results),
            "total_articles": len(all_articles),
            "processing_time_seconds": processing_time,
            "articles_per_second": articles_per_second,
            "site_breakdown": {domain: len(articles) for domain, articles in site_results.items()},
            "timestamp": datetime.now().isoformat(),
            "articles": all_articles
        }

        logger.info("🎉 Multi-site crawl summary:")
        logger.info(f"   Sites: {len(site_results)}")
        logger.info(f"   Articles: {len(all_articles)}")
        logger.info(f"   Time: {processing_time:.1f}s")
        logger.info(f"   Rate: {articles_per_second:.2f} articles/second")

        return summary


async def main():
    """Test the multi-site crawler"""
    crawler = MultiSiteCrawler(concurrent_sites=2, articles_per_site=10)
    results = await crawler.run_multi_site_crawl(max_total_articles=50)

    # Save results
    output_file = f"multi_site_crawl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"💾 Results saved to {output_file}")
    except Exception as e:
        logger.warning(f"Could not save results: {e}")


if __name__ == "__main__":
    asyncio.run(main())
