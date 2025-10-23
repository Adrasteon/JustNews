#!/usr/bin/env python3
"""
Ultra-Fast BBC Crawler for 1000+ Articles/Day

This ultra-aggressive approach prioritizes speed for production scale:
- No AI analysis (too slow for 1000+ articles)
- Pure DOM extraction with heuristic filtering
- Aggressive parallel processing
- Memory-efficient batch processing
- Cookie/modal handling optimized for speed

Target: 1000+ articles/day = ~0.7 articles/second sustained
"""

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from playwright.async_api import async_playwright

from agents.common.evidence import enqueue_human_review, snapshot_paywalled_page
from agents.common.ingest import build_article_source_map_insert, build_source_upsert
from common.observability import get_logger

# Import shared utilities
from ..crawler_utils import (
    CanonicalMetadata,
    ModalDismisser,
    RateLimiter,
    RobotsChecker,
)

logger = get_logger(__name__)

class UltraFastBBCCrawler:
    """Ultra-fast crawler optimized for 1000+ articles/day processing"""

    def __init__(self, concurrent_browsers: int = 3, batch_size: int = 20, requests_per_minute: int = 30, delay_between_requests: float = 1.0):
        self.concurrent_browsers = concurrent_browsers
        self.batch_size = batch_size
        self.rate_limiter = RateLimiter(requests_per_minute, delay_between_requests)
        self.robots_checker = RobotsChecker()
        self.news_keywords = {
            'high_value': ['arrested', 'charged', 'court', 'police', 'sentenced', 'convicted',
                          'investigation', 'crime', 'murder', 'theft', 'assault', 'fraud'],
            'medium_value': ['council', 'government', 'minister', 'mp', 'mayor', 'election',
                           'announced', 'confirmed', 'reports', 'statement', 'official'],
            'location_indicators': ['england', 'uk', 'britain', 'london', 'manchester',
                                  'birmingham', 'leeds', 'liverpool', 'bristol']
        }

    def fast_modal_dismissal_script(self) -> str:
        """Enhanced JavaScript to instantly dismiss all modals/overlays"""
        return """
        // Ultra-fast modal dismissal with comprehensive patterns
        (function() {
            // Cookie consent - comprehensive patterns
            const cookieSelectors = [
                'button:contains("Accept")', 'button:contains("I Agree")',
                'button:contains("Continue")', 'button:contains("Accept all")',
                'button:contains("Accept All")', '[data-testid="accept-all"]',
                '[id*="accept"]', '[id*="cookie"]', '.fc-cta-consent',
                '.banner-actions-button', '.cookie-banner button',
                '[class*="cookie"] button', '[class*="consent"] button'
            ];
            
            // Dismiss/close patterns - comprehensive
            const dismissSelectors = [
                'button:contains("Not now")', 'button:contains("Skip")',
                'button:contains("Maybe later")', 'button:contains("Continue without")',
                'button:contains("No thanks")', '[aria-label="Dismiss"]',
                '[aria-label="Close"]', '[aria-label="close"]',
                'button[aria-label*="close"]', '.close-button', '.modal-close',
                '[data-testid="close"]', '[data-testid="dismiss"]',
                '.close', '.dismiss', '[class*="close"]'
            ];
            
            // Try all selectors immediately with fallback methods
            const trySelector = (selector) => {
                try {
                    // CSS selector with text content
                    if (selector.includes(':contains(')) {
                        const text = selector.match(/:contains\\("([^"]+)"/)?.[1];
                        if (text) {
                            document.querySelectorAll('button, a, div[role="button"]').forEach(el => {
                                if (el.textContent.includes(text) && el.offsetParent !== null) {
                                    el.click();
                                }
                            });
                        }
                    } else {
                        // Regular selector
                        document.querySelectorAll(selector).forEach(el => {
                            if (el.offsetParent !== null) el.click();
                        });
                    }
                } catch(e) {}
            };
            
            // Execute all dismissal patterns
            [...cookieSelectors, ...dismissSelectors].forEach(trySelector);
            
            // Remove common overlay containers aggressively
            ['.modal', '.overlay', '.popup', '.banner', '.consent', 
             '.cookie-banner', '.privacy-banner', '.gdpr-banner',
             '[class*="modal"]', '[class*="overlay"]', '[class*="popup"]'
            ].forEach(cls => {
                document.querySelectorAll(cls).forEach(el => {
                    if (el.style.zIndex > 100 || 
                        el.style.position === 'fixed' || 
                        el.style.position === 'absolute') {
                        el.style.display = 'none';
                        el.remove();
                    }
                });
            });
            
            // Final cleanup: hide high z-index elements that might be modals
            document.querySelectorAll('*').forEach(el => {
                const zIndex = parseInt(window.getComputedStyle(el).zIndex);
                if (zIndex > 1000 && el.offsetParent !== null) {
                    el.style.display = 'none';
                }
            });
        })();
        """

    def calculate_news_score(self, title: str, content: str) -> float:
        """Fast heuristic news scoring (no AI needed)"""

        text = (title + " " + content).lower()
        score = 0.0

        # High-value news indicators
        for keyword in self.news_keywords['high_value']:
            if keyword in text:
                score += 0.3

        # Medium-value indicators
        for keyword in self.news_keywords['medium_value']:
            if keyword in text:
                score += 0.15

        # Location relevance
        for location in self.news_keywords['location_indicators']:
            if location in text:
                score += 0.1

        # Structure indicators
        if len(content) > 200:
            score += 0.2
        if re.search(r'\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}', text):  # Dates
            score += 0.1
        if 'bbc' in text:
            score += 0.1

        return min(score, 1.0)

    async def ultra_fast_extract(self, page) -> dict[str, str]:
        """Ultra-fast content extraction optimized for speed"""

        try:
            # Inject modal dismissal script immediately
            await page.evaluate(self.fast_modal_dismissal_script())

            # Also use shared modal dismisser
            await ModalDismisser.dismiss_modals(page)

            # Get title (fast)
            title = await page.title()

            # Fast content extraction with timeout
            content = ""
            try:
                # Try main content areas with short timeout
                content_elem = await page.locator('main, [role="main"], .story-body').first.text_content(timeout=2000)
                content = content_elem[:800] if content_elem else ""
            except Exception:
                # Fallback to paragraphs
                try:
                    paragraphs = await page.locator('p').all_text_contents(timeout=1000)
                    content = " ".join(paragraphs[:3])  # First 3 paragraphs only
                except Exception:
                    content = ""

            # Attempt to quickly extract canonical link and paywall signals
            canonical, paywall_flag = await CanonicalMetadata.extract_canonical_and_paywall(page)

            extraction_metadata = {
                'method': 'ultra_fast_dom',
                'extracted_length': len(content or ''),
            }

            return {
                "title": title,
                "content": content,
                "extraction_time": time.time(),
                "canonical": canonical,
                "paywall_flag": paywall_flag,
                "extraction_metadata": extraction_metadata
            }

        except Exception as e:
            return {
                "title": "Error",
                "content": f"Extraction failed: {e}",
                "extraction_time": time.time()
            }

    async def process_url_ultra_fast(self, browser, url: str) -> dict | None:
        """Ultra-fast single URL processing"""

        try:
            # Check robots.txt compliance first
            if not self.robots_checker.check_robots_txt(url):
                logger.info(f"⚠️ Robots.txt disallows crawling: {url}")
                return CanonicalMetadata.generate_metadata(
                    url=url,
                    title="Robots.txt Disallowed",
                    content="Crawling not allowed by robots.txt",
                    extraction_method="disallowed",
                    status="disallowed",
                    paywall_flag=False,
                    confidence=0.0,
                    publisher="BBC",
                    crawl_mode="ultra_fast",
                    news_score=0.0,
                    error="robots_disallowed"
                )

            # Apply rate limiting
            domain = urlparse(url).netloc
            await self.rate_limiter.wait_if_needed(domain)

            # Fast context creation
            context = await browser.new_context(
                viewport={'width': 1024, 'height': 768},
                java_script_enabled=True
            )
            page = await context.new_page()

            # Navigate with aggressive timeout
            await page.goto(url, wait_until='domcontentloaded', timeout=8000)

            # Ultra-fast content extraction
            content_data = await self.ultra_fast_extract(page)

            # Close immediately
            await context.close()

            # Throttle per-article to reduce crawling speed: random sleep 1-3 seconds
            try:
                delay = random.uniform(1.0, 3.0)
                await asyncio.sleep(delay)
            except Exception:
                pass

            # Fast news scoring
            news_score = self.calculate_news_score(content_data["title"], content_data["content"])

            # Only keep high-quality news (threshold for speed)
            if news_score >= 0.4 and len(content_data["content"]) > 100:

                # Enrichment: url_hash, domain, canonical, publisher_meta (minimal), paywall flag
                domain = urlparse(url).netloc
                canonical = content_data.get('canonical')
                paywall_flag = content_data.get('paywall_flag', False)

                return CanonicalMetadata.generate_metadata(
                    url=url,
                    title=content_data["title"],
                    content=content_data["content"],
                    extraction_method="ultra_fast_dom",
                    status="success",
                    paywall_flag=paywall_flag,
                    confidence=news_score,
                    publisher="BBC",
                    crawl_mode="ultra_fast",
                    news_score=news_score,
                    canonical=canonical
                )

            return None  # Filtered out

        except Exception as e:
            return CanonicalMetadata.generate_metadata(
                url=url,
                title="Error",
                content=f"Processing failed: {e}",
                extraction_method="error",
                status="error",
                paywall_flag=False,
                confidence=0.0,
                publisher="BBC",
                crawl_mode="ultra_fast",
                news_score=0.0,
                error=str(e)
            )

    async def get_urls_ultra_fast(self, max_urls: int = 200) -> list[str]:
        """Get URLs as fast as possible"""

        browser = await async_playwright().start()
        browser_instance = await browser.chromium.launch(headless=True)

        try:
            context = await browser_instance.new_context()
            page = await context.new_page()

            # Navigate with timeout
            await page.goto("https://www.bbc.co.uk/news/england", timeout=10000)

            # Dismiss modals
            await page.evaluate(self.fast_modal_dismissal_script())
            await asyncio.sleep(1)

            # Extract links fast
            links = await page.evaluate("""
                () => {
                    return Array.from(document.querySelectorAll('a[href*="articles/"]'))
                        .map(a => a.href)
                        .filter(href => href.includes('articles/'))
                        .slice(0, 200);
                }
            """)

            await browser_instance.close()

            logger.info(f"⚡ Found {len(links)} URLs in record time")
            return links

        except Exception as e:
            logger.error(f"URL extraction failed: {e}")
            await browser_instance.close()
            return []

    async def process_ultra_fast_batch(self, urls: list[str]) -> list[dict]:
        """Process batches with maximum parallelization"""

        # Create multiple browser instances for parallel processing
        playwright = await async_playwright().start()
        browsers = []

        try:
            # Launch multiple browsers
            for _ in range(self.concurrent_browsers):
                browser = await playwright.chromium.launch(headless=True)
                browsers.append(browser)

            logger.info(f"🚀 Processing {len(urls)} URLs with {len(browsers)} concurrent browsers")

            results = []
            browser_index = 0

            # Process in aggressive batches
            for i in range(0, len(urls), self.batch_size):
                batch_urls = urls[i:i + self.batch_size]
                batch_start = time.time()

                # Distribute URLs across browsers
                tasks = []
                for url in batch_urls:
                    browser = browsers[browser_index % len(browsers)]
                    browser_index += 1
                    tasks.append(self.process_url_ultra_fast(browser, url))

                # Process batch concurrently
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Collect successful results
                successful_in_batch = 0
                for result in batch_results:
                    if isinstance(result, dict) and result.get("status") == "success":
                        results.append(result)
                        successful_in_batch += 1

                batch_time = time.time() - batch_start
                rate = len(batch_urls) / batch_time if batch_time > 0 else 0

                logger.info(f"⚡ Batch {i//self.batch_size + 1}: {successful_in_batch}/{len(batch_urls)} success, {rate:.1f} URLs/sec")

                # Minimal delay between batches
                await asyncio.sleep(0.1)

            return results

        finally:
            # Close all browsers
            for browser in browsers:
                await browser.close()

    async def run_ultra_fast_crawl(self, target_articles: int = 200, skip_ingestion: bool = False):
        """Main ultra-fast crawling function"""

        start_time = time.time()
        logger.info(f"🚀 Ultra-Fast BBC Crawl: Target {target_articles} articles")

        # Get URLs fast
        urls = await self.get_urls_ultra_fast(max_urls=target_articles * 2)  # Get extra for filtering

        if not urls:
            logger.error("❌ No URLs found!")
            return []

        # Process ultra-fast
        results = await self.process_ultra_fast_batch(urls)

        # Save results
        total_time = time.time() - start_time
        output_file = f"ultra_fast_bbc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        summary = {
            "ultra_fast_crawl": True,
            "target_articles": target_articles,
            "urls_processed": len(urls),
            "successful_articles": len(results),
            "total_time_seconds": total_time,
            "articles_per_second": len(results) / total_time if total_time > 0 else 0,
            "success_rate": len(results) / len(urls) if urls else 0.0,
            "projected_daily_capacity": (len(results) / total_time) * 86400 if total_time > 0 else 0,
            "timestamp": datetime.now().isoformat(),
            "articles": results  # Use 'articles' key to match orchestrator expectation
        }

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save results file: {e}")

        logger.info("🎉 Ultra-Fast Crawl Complete!")
        logger.info(f"📊 {len(results)} articles in {total_time:.1f}s")
        logger.info(f"⚡ Rate: {len(results) / total_time:.2f} articles/second")
        logger.info(f"✅ Success Rate: {len(results) / len(urls) * 100:.1f}%")
        logger.info(f"Daily capacity: {(len(results) / total_time) * 86400:.0f} articles/day")

        # Dispatch ingest requests to DB worker via MCP Bus (best-effort).
        MCP_BUS_URL = os.environ.get('MCP_BUS_URL', 'http://localhost:8000')

        if not skip_ingestion:
            async def dispatch_ingest(article: dict):
                # Build article payload and DB statements
                # If article is paywalled, snapshot and enqueue for human review instead of ingesting
                if article.get('paywall_flag'):
                    try:
                        html_stub = article.get('content', '')
                        metadata = {
                            'title': article.get('title'),
                            'domain': article.get('domain'),
                            'url': article.get('url'),
                            'timestamp': article.get('timestamp')
                        }
                        evidence_path = snapshot_paywalled_page(article.get('url'), html_stub, metadata)
                        enqueue_human_review(evidence_path, reviewer='chief_editor')
                        logger.info(f"Paywalled article snapshot saved and enqueued for review: {article.get('url')}")
                    except Exception as e:
                        logger.warning(f"Failed to snapshot/enqueue paywalled article {article.get('url')}: {e}")
                    return

                article_payload = {
                    'url': article.get('url'),
                    'url_hash': article.get('url_hash'),
                    'domain': article.get('domain'),
                    'canonical': article.get('canonical'),
                    'publisher_meta': {'publisher': 'BBC'},
                    'confidence': article.get('confidence', 0.5),
                    'paywall_flag': article.get('paywall_flag', False),
                    'extraction_metadata': article.get('extraction_metadata', {}),
                    'timestamp': article.get('timestamp'),
                    # article_id is not created here; let DB worker or orchestrator assign
                }

                source_sql, source_params = build_source_upsert(article_payload)
                asm_sql, asm_params = build_article_source_map_insert(article_payload.get('article_id', 1), article_payload)

                # Convert params tuples to lists for JSON serialization
                statements = [ [source_sql, list(source_params)], [asm_sql, list(asm_params)] ]

                payload = {
                    'agent': 'memory',
                    'tool': 'ingest_article',
                    'args': [],
                    'kwargs': {
                        'article_payload': article_payload,
                        'statements': statements
                    }
                }

                loop = asyncio.get_running_loop()

                def do_call():
                    try:
                        resp = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=(2, 10))
                        resp.raise_for_status()
                        return resp.json()
                    except Exception as e:
                        logger.warning(f"DB worker call failed for {article.get('url')}: {e}")
                        return None

                res = await loop.run_in_executor(None, do_call)
                if res:
                    logger.info(f"Ingest dispatched for {article.get('url')}: {res}")

            # Fire off ingestion tasks concurrently (not awaiting per-article network delays)
            try:
                tasks = [dispatch_ingest(a) for a in results]
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                logger.warning(f"Error dispatching ingest tasks: {e}")

        return summary

async def main():
    """Run ultra-fast crawler"""
    crawler = UltraFastBBCCrawler(concurrent_browsers=3, batch_size=15)
    await crawler.run_ultra_fast_crawl(target_articles=100, skip_ingestion=False)

if __name__ == "__main__":
    asyncio.run(main())
