#!/usr/bin/env python3
"""
Crawler Engine for JustNewsAgent

Unified production crawler that combines all crawling strategies
into a single intelligent system.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import requests

# Database imports
from common.observability import get_logger
from ..sites.generic_site_crawler import GenericSiteCrawler, MultiSiteCrawler, SiteConfig
from .crawler_utils import (
    CanonicalMetadata,
    ModalDismisser,
    RateLimiter,
    RobotsChecker,
    get_active_sources,
    get_sources_by_domain,
    update_source_crawling_strategy,
    record_crawling_performance,
    get_source_performance_history,
    get_optimal_sources_for_strategy,
    create_crawling_performance_table,
    initialize_connection_pool,
)
from ..performance_monitoring import (
    PerformanceMetrics,
    PerformanceOptimizer,
    get_performance_monitor,
    start_performance_monitoring,
    stop_performance_monitoring,
    export_performance_metrics
)

MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

def call_analyst_tool(tool: str, *args, **kwargs) -> Any:
    payload = {"agent": "analyst", "tool": tool, "args": list(args), "kwargs": kwargs}
    resp = requests.post(f"{MCP_BUS_URL}/call", json=payload)
    resp.raise_for_status()
    return resp.json().get("data")

logger = get_logger(__name__)


class CrawlerEngine:
    """
    Unified production crawler that combines all crawling strategies
    into a single intelligent system.

    Features:
    - Intelligent mode selection per site
    - Comprehensive AI analysis pipeline
    - Multi-site concurrent processing
    - Database-driven source management
    - Performance monitoring and metrics
    """

    def __init__(self):
        # Initialize core components
        self.rate_limiter = RateLimiter()
        self.robots_checker = RobotsChecker()

        # AI analysis delegated to Analyst agent; no local model state

        # Crawling components
        self.multi_site_crawler = MultiSiteCrawler()
        self.site_strategies = {}  # Cache for site-specific strategies

        # Performance monitoring
        self.performance_monitor = get_performance_monitor()
        self.performance_optimizer = PerformanceOptimizer(self.performance_monitor)
        # Initialize performance metrics tracking
        import time
        self.performance_metrics = {
            "start_time": time.time(),
            "articles_processed": 0,
            "sites_crawled": 0,
            "errors": 0,
            "mode_usage": {"ultra_fast": 0, "ai_enhanced": 0, "generic": 0}
        }

        # Start monitoring if enabled
        if os.environ.get("UNIFIED_CRAWLER_PERFORMANCE_MONITORING", "true").lower() == "true":
            start_performance_monitoring(interval_seconds=60)

        # Initialize database connection and performance table
        try:
            initialize_connection_pool()
            create_crawling_performance_table()
            logger.info("✅ Database connection pool and performance table initialized")
        except Exception as e:
            logger.warning(f"⚠️ Database initialization failed (crawler will work without performance tracking): {e}")
            # Continue without database - crawler can still work via MCP bus

        # Strategy optimization cache
        self.strategy_cache = {}
        self.performance_history = {}

        # Background cleanup management
        self.cleanup_task = None
        self._start_background_cleanup()

    def _start_background_cleanup(self):
        """Start background cleanup task - disabled to prevent conflicts with async context manager"""
        # Background cleanup disabled - cleanup is now handled by async context manager
        # which is more reliable and prevents process accumulation
        pass

    async def _periodic_cleanup(self):
        """Run periodic cleanup every 30 seconds"""
        while True:
            try:
                await self._cleanup_orphaned_processes()
                await asyncio.sleep(30)  # Clean every 30 seconds
            except Exception as e:
                logger.debug(f"Periodic cleanup failed: {e}")
                await asyncio.sleep(30)

    async def _cleanup_orphaned_processes(self):
        """Aggressively cleanup orphaned browser processes - only kill very old processes"""
        try:
            import subprocess
            import signal
            import os

            # Kill Chrome processes older than 10 minutes (very conservative)
            try:
                result = subprocess.run(
                    ['pgrep', '-f', 'chrome'],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    pids = result.stdout.strip().split('\n')
                    cleaned_count = 0
                    for pid in pids:
                        if not pid.strip():
                            continue
                        try:
                            # Check process age
                            stat_result = subprocess.run(
                                ['ps', '-o', 'etimes=', '-p', pid],
                                capture_output=True, text=True, timeout=2
                            )
                            if stat_result.returncode == 0:
                                etime = int(stat_result.stdout.strip())
                                if etime > 600:  # 10 minutes - very conservative
                                    os.kill(int(pid), signal.SIGTERM)
                                    cleaned_count += 1
                                    logger.debug(f"Cleaned up very old Chrome process {pid} (age: {etime}s)")
                        except (ValueError, ProcessLookupError):
                            # Process already gone
                            pass
                    if cleaned_count > 0:
                        logger.info(f"Cleaned up {cleaned_count} very old Chrome processes")
            except subprocess.TimeoutExpired:
                logger.debug("Chrome cleanup timed out")
            except Exception as e:
                logger.debug(f"Chrome cleanup failed: {e}")

            # Kill Playwright driver processes older than 15 minutes
            try:
                result = subprocess.run(
                    ['pgrep', '-f', 'playwright.*run-driver'],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if not pid.strip():
                            continue
                        try:
                            # Check if Playwright driver is very old
                            stat_result = subprocess.run(
                                ['ps', '-o', 'etimes=', '-p', pid],
                                capture_output=True, text=True, timeout=2
                            )
                            if stat_result.returncode == 0:
                                etime = int(stat_result.stdout.strip())
                                if etime > 900:  # 15 minutes for Playwright drivers
                                    os.kill(int(pid), signal.SIGTERM)
                                    logger.debug(f"Cleaned up very old Playwright driver {pid}")
                        except (ValueError, ProcessLookupError):
                            pass
            except subprocess.TimeoutExpired:
                logger.debug("Playwright cleanup timed out")
            except Exception as e:
                logger.debug(f"Playwright cleanup failed: {e}")

        except Exception as e:
            logger.warning(f"Orphaned process cleanup failed: {e}")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources"""
        await self._cleanup()

    async def _cleanup(self):
        """Cleanup all resources"""
        try:
            # Cancel background cleanup task
            if self.cleanup_task and not self.cleanup_task.done():
                self.cleanup_task.cancel()
                try:
                    await self.cleanup_task
                except asyncio.CancelledError:
                    pass

            # Final aggressive cleanup - kill all browser processes from this session
            await self._cleanup_orphaned_processes()

            # Force kill any remaining processes - be more aggressive here
            import subprocess
            try:
                # Kill all Chrome processes (they should all be from this crawler instance)
                subprocess.run(['pkill', '-9', '-f', 'chrome'],
                             timeout=10, capture_output=True)
                # Kill Playwright drivers
                subprocess.run(['pkill', '-9', '-f', 'playwright.*run-driver'],
                             timeout=10, capture_output=True)
                logger.info("Forced cleanup of all browser processes from crawler session")
            except subprocess.TimeoutExpired:
                logger.warning("Force cleanup timed out")
            except Exception as e:
                logger.debug(f"Force cleanup failed: {e}")

        except Exception as e:
            logger.warning(f"Resource cleanup failed: {e}")

    async def _load_ai_models(self):
        """No-op stub: AI model loading handled by GPU Orchestrator"""
        return

    async def _determine_optimal_strategy(self, site_config: SiteConfig) -> str:
        """
        Determine optimal crawling strategy based on site characteristics and performance history

        Uses performance data to optimize strategy selection dynamically.
        """

        domain = site_config.domain.lower()
        source_id = site_config.source_id

        # Check cache first
        cache_key = f"{domain}_{source_id}"
        if cache_key in self.strategy_cache:
            return self.strategy_cache[cache_key]

        # Get performance history for this source
        if source_id:
            performance_history = get_source_performance_history(source_id, limit=5)
            if performance_history:
                # Calculate average performance by strategy
                strategy_performance = {}
                for record in performance_history:
                    strategy = record['strategy_used']
                    if strategy not in strategy_performance:
                        strategy_performance[strategy] = []
                    strategy_performance[strategy].append(record['articles_per_second'])

                # Find best performing strategy
                best_strategy = None
                best_avg_performance = 0

                for strategy, performances in strategy_performance.items():
                    avg_performance = sum(performances) / len(performances)
                    if avg_performance > best_avg_performance:
                        best_avg_performance = avg_performance
                        best_strategy = strategy

                if best_strategy and best_avg_performance > 0.1:  # Minimum threshold
                    self.strategy_cache[cache_key] = best_strategy
                    logger.info(f"🎯 Using performance-optimized strategy for {domain}: {best_strategy} ({best_avg_performance:.2f} articles/sec)")
                    return best_strategy

        # Fallback to rule-based strategy selection
        ultra_fast_domains = [
            'bbc.com', 'bbc.co.uk', 'cnn.com', 'reuters.com',
            'apnews.com', 'npr.org', 'nytimes.com', 'washingtonpost.com'
        ]

        ai_enhanced_domains = [
            'wsj.com', 'ft.com', 'economist.com', 'newyorker.com',
            'theatlantic.com', 'foreignaffairs.com'
        ]

        # 1. Check for pre-defined ultra-fast sites
        # These are high-volume, well-structured sites with dedicated parsers
        if any(d in domain for d in ["bbc.co.uk", "cnn.com", "reuters.com"]):
            return "ultra_fast"

        # Force AI-enhanced for known complex/paywalled sites
        if any(d in domain for d in ["nytimes.com", "wsj.com", "washingtonpost.com", "theatlantic.com", "newyorker.com"]):
            logger.info(f"Found known complex site {domain}, forcing 'ai_enhanced' strategy.")
            return "ai_enhanced"

        # 2. Check database for historical performance
        if domain not in self.performance_history:
            self.performance_history[domain] = get_source_performance_history(domain)

        # Default to generic strategy
        return "generic"

    async def _crawl_ultra_fast_mode(self, site_config: SiteConfig, max_articles: int = 50) -> List[Dict]:
        """
        Ultra-fast crawling mode (8.14+ articles/sec)
        Optimized for high-volume sites with reliable structure
        """
        logger.info(f"🚀 Ultra-fast crawling: {site_config.name}")

        try:
            # Try to import ultra-fast BBC crawler for BBC sites
            if 'bbc' in site_config.domain.lower():
                try:
                    from ..sites.bbc_crawler import UltraFastBBCCrawler
                    crawler = UltraFastBBCCrawler()
                    results = await crawler.run_ultra_fast_crawl(max_articles, skip_ingestion=True)
                    self.performance_metrics["mode_usage"]["ultra_fast"] += 1
                    # BBC crawler returns summary with 'articles' key and handles its own ingestion
                    return results.get('articles', [])
                except ImportError:
                    logger.warning("Ultra-fast BBC crawler not available, falling back to generic")
                finally:
                    # Cleanup after BBC crawler
                    await self._cleanup_orphaned_processes()

            # Fallback to optimized generic crawling
            crawler = GenericSiteCrawler(site_config, concurrent_browsers=3, batch_size=10)
            articles = await crawler.crawl_site(max_articles)

            self.performance_metrics["mode_usage"]["ultra_fast"] += 1
            return articles

        except Exception as e:
            logger.error(f"Ultra-fast crawling failed for {site_config.name}: {e}")
            return []
        finally:
            # Always cleanup after ultra-fast mode
            await self._cleanup_orphaned_processes()

    async def _crawl_ai_enhanced_mode(self, site_config: SiteConfig, max_articles: int = 25) -> List[Dict]:
        """AI-enhanced crawling stub: delegates to generic mode"""
        logger.info(f"🤖 AI-enhanced crawling stub: delegating to generic mode for {site_config.name}")
        try:
            articles = await self._crawl_generic_mode(site_config, max_articles)
            self.performance_metrics["mode_usage"]["ai_enhanced"] += 1
            return articles
        finally:
            # Always cleanup after AI-enhanced crawling
            await self._cleanup_orphaned_processes()

    async def _crawl_generic_mode(self, site_config: SiteConfig, max_articles: int = 25) -> List[Dict]:
        """
        Generic crawling mode with Crawl4AI-first strategy
        Supports any news source with graceful fallbacks
        """
        logger.info(f"🌐 Generic crawling: {site_config.name}")

        try:
            crawler = GenericSiteCrawler(site_config, concurrent_browsers=2, batch_size=8)
            articles = await crawler.crawl_site(max_articles)

            self.performance_metrics["mode_usage"]["generic"] += 1
            return articles

        except Exception as e:
            logger.error(f"Generic crawling failed for {site_config.name}: {e}")
            return []
        finally:
            # Always cleanup after generic crawling
            await self._cleanup_orphaned_processes()

    async def _apply_ai_analysis(self, article: Dict) -> Dict:
        """Delegate AI analysis to Analyst agent via MCP bus"""
        content = article.get('content', '')
        if not content or len(content) < 100:
            return article
        try:
            sentiment_score = call_analyst_tool('score_sentiment', content)
            article['sentiment'] = {'score': sentiment_score}
            topics = call_analyst_tool('extract_topics', content)
            article['topics'] = topics
            article['ai_analysis_applied'] = True
        except Exception as e:
            logger.error(f"Remote AI analysis failed: {e}")
        return article

    async def crawl_site(self, site_config: SiteConfig, max_articles: int = 25) -> List[Dict]:
        """
        Crawl a single site using the optimal strategy
        """
        strategy = await self._determine_optimal_strategy(site_config)

        if strategy == 'ultra_fast':
            return await self._crawl_ultra_fast_mode(site_config, max_articles)
        elif strategy == 'ai_enhanced':
            return await self._crawl_ai_enhanced_mode(site_config, max_articles)
        else:  # generic
            return await self._crawl_generic_mode(site_config, max_articles)

    async def run_unified_crawl(self, domains: List[str], max_articles_per_site: int = 25, concurrent_sites: int = 3) -> Dict[str, Any]:
        """
        Main entry point for unified crawling - converts domains to SiteConfig objects and runs crawl
        """
        logger.info(f"🚀 Starting unified crawl for domains: {domains}")

        # Convert domains to SiteConfig objects
        site_configs = []
        for domain in domains:
            if isinstance(domain, list):
                domain = domain[0] if domain else ""
            try:
                # Get source info from database
                sources = get_sources_by_domain([domain])  # Pass as list
                if sources:
                    source = sources[0]  # Use first match
                    config = SiteConfig(source)
                    site_configs.append(config)
                else:
                    # Create basic config for unknown domains
                    logger.warning(f"No database entry for {domain}, creating basic config")
                    parsed = urlparse(domain)
                    if parsed.scheme and parsed.netloc:
                        fallback_domain = parsed.netloc
                        fallback_url = domain
                    else:
                        fallback_domain = domain
                        fallback_url = f"https://{domain}" if domain else ""

                    config = SiteConfig({
                        'id': None,
                        'name': fallback_domain or domain or 'unknown',
                        'domain': fallback_domain,
                        'url': fallback_url,
                        'crawling_strategy': 'generic'
                    })
                    site_configs.append(config)
            except Exception as e:
                logger.error(f"Failed to create config for {domain}: {e}")
                continue

        if not site_configs:
            logger.error("❌ No valid site configurations created")
            return {"error": "No valid domains provided"}

        # Execute the crawl
        return await self.crawl_multiple_sites(site_configs, max_articles_per_site, concurrent_sites)

    async def crawl_multiple_sites(self, site_configs: List[SiteConfig],
                                 max_articles_per_site: int = 25,
                                 concurrent_sites: int = 3) -> Dict[str, Any]:
        """
        Crawl multiple sites concurrently using optimal strategies
        """
        logger.info(f"🚀 Starting unified multi-site crawl: {len(site_configs)} sites")

        start_time = time.time()
        results = {}
        semaphore = asyncio.Semaphore(concurrent_sites)

        async def crawl_site_with_limit(site_config: SiteConfig):
            async with semaphore:
                try:
                    articles = await self.crawl_site(site_config, max_articles_per_site)
                    results[site_config.domain] = articles
                    self.performance_metrics["articles_processed"] += len(articles)
                    self.performance_metrics["sites_crawled"] += 1
                    logger.info(f"🏁 Completed {site_config.name}: {len(articles)} articles")
                finally:
                    # Cleanup after each site crawl
                    await self._cleanup_orphaned_processes()

        # Execute concurrently
        tasks = [crawl_site_with_limit(config) for config in site_configs]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Calculate performance metrics
        total_time = time.time() - start_time
        total_articles = sum(len(articles) for articles in results.values())
        articles_per_second = total_articles / total_time if total_time > 0 else 0

        # Flatten results for easier processing
        all_articles = []
        for domain, articles in results.items():
            all_articles.extend(articles)

        # Ingest articles to database via memory agent
        ingest_results = {'new_articles': 0, 'duplicates': 0, 'errors': 0}
        if all_articles:
            ingest_results = await self._ingest_articles(all_articles)
            logger.info(f"📥 Ingested {ingest_results['new_articles']} new articles, {ingest_results['duplicates']} duplicates, {ingest_results['errors']} errors")

        summary = {
            "unified_crawl": True,
            "sites_crawled": len(results),
            "total_articles": total_articles,
            "articles_ingested": ingest_results['new_articles'],
            "duplicates_skipped": ingest_results['duplicates'],
            "ingestion_errors": ingest_results['errors'],
            "processing_time_seconds": total_time,
            "articles_per_second": articles_per_second,
            "strategy_breakdown": self.performance_metrics["mode_usage"],
            "site_breakdown": {domain: len(articles) for domain, articles in results.items()},
            "articles": all_articles  # Include the actual articles
        }

        logger.info(f"✅ Unified crawl completed: {total_articles} articles in {total_time:.2f}s ({articles_per_second:.2f} articles/sec)")
        return summary

    async def _ingest_articles(self, articles: List[Dict]) -> Dict[str, int]:
        """
        Ingest articles to database via memory agent MCP calls

        Returns:
            Dict with counts: {'new_articles': int, 'duplicates': int, 'errors': int}
        """
        MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
        new_articles = 0
        duplicates = 0
        errors = 0

        for article in articles:
            try:
                # Prepare article payload for ingestion
                article_payload = {
                    'url': article.get('url', ''),
                    'title': article.get('title', ''),
                    'content': article.get('content', ''),
                    'domain': article.get('domain', ''),
                    'publisher_meta': article.get('publisher_meta', {}),
                    'confidence': article.get('confidence', 0.5),
                    'paywall_flag': article.get('paywall_flag', False),
                    'extraction_metadata': article.get('extraction_metadata', {}),
                    'extracted_metadata': article.get('extracted_metadata', {}),
                    'structured_metadata': article.get('structured_metadata', {}),
                    'language': article.get('language'),
                    'authors': article.get('authors', []),
                    'section': article.get('section'),
                    'tags': article.get('tags', []),
                    'publication_date': article.get('publication_date'),
                    'raw_html_ref': article.get('raw_html_ref'),
                    'timestamp': article.get('timestamp'),
                    'url_hash': article.get('url_hash'),
                    'canonical': article.get('canonical'),
                }

                # Build SQL statements for source upsert and article insertion
                # This mirrors the logic from the site-specific crawlers
                source_sql = """
                INSERT INTO sources (name, domain, url, last_verified, metadata)
                VALUES (%s, %s, %s, NOW(), %s)
                RETURNING id
                """

                source_params = (
                    article.get('source_name', article.get('domain', 'unknown')),
                    article.get('domain', 'unknown'),
                    f"https://{article.get('domain', 'unknown')}",
                    json.dumps({'crawling_strategy': 'unified_crawler', 'last_crawled': article.get('timestamp')})
                )

                # Article insertion SQL (will be handled by memory agent)
                # The memory agent handles the article insertion via save_article

                statements = [
                    [source_sql, list(source_params)]
                ]

                payload = {
                    'agent': 'memory',
                    'tool': 'ingest_article',
                    'args': [],
                    'kwargs': {
                        'article_payload': article_payload,
                        'statements': statements
                    }
                }

                # Make MCP bus call to memory agent
                response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=(2, 10))
                response.raise_for_status()
                result = response.json()

                outer_status = result.get('status')
                inner_payload = result.get('data') if isinstance(result.get('data'), dict) else {}
                effective_payload = inner_payload if inner_payload else result
                inner_status = effective_payload.get('status', outer_status)

                if outer_status in {"ok", "success"} and inner_status in {"ok", "success"}:
                    if effective_payload.get('duplicate'):
                        duplicates += 1
                        logger.debug(f"Duplicate article skipped: {article.get('url')}")
                    else:
                        new_articles += 1
                        logger.debug(f"New article ingested: {article.get('url')}")
                else:
                    errors += 1
                    logger.warning(f"Failed to ingest article {article.get('url')}: {result}")

            except Exception as e:
                errors += 1
                logger.warning(f"Error ingesting article {article.get('url', 'unknown')}: {e}")
                continue

        return {'new_articles': new_articles, 'duplicates': duplicates, 'errors': errors}

    def get_performance_report(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        return {
            "articles_processed": self.performance_metrics["articles_processed"],
            "sites_crawled": self.performance_metrics["sites_crawled"],
            "errors": self.performance_metrics["errors"],
            "mode_usage": self.performance_metrics["mode_usage"],
            "uptime_seconds": time.time() - self.performance_metrics["start_time"]
        }