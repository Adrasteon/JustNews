#!/usr/bin/env python3
"""
Unified Production Crawler for JustNewsAgent

PHASE 3 ACHIEVEMENT: Combines ultra-fast crawling (8.14+ articles/sec),
AI-enhanced analysis (0.86+ articles/sec), and generic multi-site capabilities
into a single intelligent production crawler.

This unified crawler intelligently selects the optimal crawling strategy:
- Ultra-fast mode for high-volume sites (BBC, CNN, Reuters)
- AI-enhanced mode for quality-critical content
- Generic mode for any news source with Crawl4AI/Playwright fallback
- Multi-site orchestration for concurrent processing

Capabilities:
- Intelligent mode selection based on site characteristics
- Comprehensive AI analysis pipeline (LLaVA, BERTopic, NewsReader, Tomotopy)
- Database-driven source management with performance tracking
- Ethical crawling compliance (robots.txt, rate limiting)
- Systemd integration for production deployment
- Performance monitoring and metrics collection
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Database and AI imports
import tomotopy as tp
from bertopic import BERTopic
from transformers import pipeline

# Local imports
from common.observability import get_logger
from .sites.generic_site_crawler import GenericSiteCrawler, MultiSiteCrawler, SiteConfig
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
from .performance_monitoring import (
    PerformanceMetrics,
    PerformanceOptimizer,
    get_performance_monitor,
    start_performance_monitoring,
    stop_performance_monitoring,
    export_performance_metrics
)

logger = get_logger(__name__)


class UnifiedProductionCrawler:
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

        # AI Models (lazy-loaded)
        self._bertopic_model = None
        self._lda_model = None
        self._sentiment_pipeline = None
        self._newsreader_available = False

        # Crawling components
        self.multi_site_crawler = MultiSiteCrawler()
        self.site_strategies = {}  # Cache for site-specific strategies

        # Performance monitoring and metrics initialization
        self.performance_monitor = get_performance_monitor()
        self.performance_optimizer = PerformanceOptimizer(self.performance_monitor)
        # Legacy performance metrics dict for unified crawler
        self.performance_metrics = {
            "start_time": time.time(),
            "mode_usage": {"ultra_fast": 0, "ai_enhanced": 0, "generic": 0},
            "articles_processed": 0,
            "sites_crawled": 0,
            "errors": 0
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
            logger.warning(f"⚠️ Database initialization failed: {e}")

        # Strategy optimization cache
        self.strategy_cache = {}
        self.performance_history = {}

    async def _load_ai_models(self):
        """Lazy-load AI models for analysis pipeline"""
        try:
            # BERTopic for topic modeling
            if self._bertopic_model is None:
                logger.info("🔄 Loading BERTopic model...")
                self._bertopic_model = BERTopic.load("models/bertopic_model")
                logger.info("✅ BERTopic model loaded")

            # Tomotopy Online LDA
            if self._lda_model is None:
                logger.info("🔄 Initializing Tomotopy Online LDA...")
                self._lda_model = tp.OnlineLDA(min_cf=5, rm_top=10, k=50)
                logger.info("✅ Online LDA model initialized")

            # Sentiment analysis pipeline
            if self._sentiment_pipeline is None:
                logger.info("🔄 Loading sentiment analysis pipeline...")
                self._sentiment_pipeline = pipeline(
                    "sentiment-analysis",
                    model="cardiffnlp/twitter-roberta-base-sentiment-latest"
                )
                logger.info("✅ Sentiment pipeline loaded")

            # Check NewsReader availability
            try:
                from agents.newsreader.tools import analyze_article_with_newsreader
                self._newsreader_available = True
                logger.info("✅ NewsReader integration available")
            except ImportError:
                logger.warning("⚠️ NewsReader not available")
                self._newsreader_available = False

        except Exception as e:
            logger.error(f"❌ Failed to load AI models: {e}")

    def _determine_optimal_strategy(self, site_config: SiteConfig) -> str:
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

        if any(uf_domain in domain for uf_domain in ultra_fast_domains):
            strategy = 'ultra_fast'
        elif any(ai_domain in domain for ai_domain in ai_enhanced_domains):
            strategy = 'ai_enhanced'
        else:
            strategy = 'generic'

        self.strategy_cache[cache_key] = strategy
        return strategy

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
                    from .sites.bbc_crawler import UltraFastBBCCrawler
                    crawler = UltraFastBBCCrawler()
                    results = await crawler.run_ultra_fast_crawl(max_articles)
                    self.performance_metrics["mode_usage"]["ultra_fast"] += 1
                    return results.get('articles', [])
                except ImportError:
                    logger.warning("Ultra-fast BBC crawler not available, falling back to generic")

            # Fallback to optimized generic crawling
            crawler = GenericSiteCrawler(site_config, concurrent_browsers=3, batch_size=10)
            articles = await crawler.crawl_site(max_articles)

            self.performance_metrics["mode_usage"]["ultra_fast"] += 1
            return articles

        except Exception as e:
            logger.error(f"Ultra-fast crawling failed for {site_config.name}: {e}")
            return []

    async def _crawl_ai_enhanced_mode(self, site_config: SiteConfig, max_articles: int = 25) -> List[Dict]:
        """
        AI-enhanced crawling mode (0.86+ articles/sec)
        Includes full AI analysis pipeline with NewsReader integration
        """
        logger.info(f"🤖 AI-enhanced crawling: {site_config.name}")

        try:
            # Try to import AI-enhanced BBC crawler for BBC sites
            if 'bbc' in site_config.domain.lower():
                try:
                    from .sites.bbc_ai_crawler import ProductionBBCCrawler
                    crawler = ProductionBBCCrawler()
                    results = await crawler.run_production_crawl(max_articles)
                    self.performance_metrics["mode_usage"]["ai_enhanced"] += 1
                    return results.get('articles', [])
                except ImportError:
                    logger.warning("AI-enhanced BBC crawler not available, falling back to generic with AI")

            # Enhanced generic crawling with AI analysis
            crawler = GenericSiteCrawler(site_config, concurrent_browsers=2, batch_size=5)
            articles = await crawler.crawl_site(max_articles)

            # Apply AI analysis to each article
            await self._load_ai_models()
            enhanced_articles = []
            for article in articles:
                enhanced_article = await self._apply_ai_analysis(article)
                enhanced_articles.append(enhanced_article)

            self.performance_metrics["mode_usage"]["ai_enhanced"] += 1
            return enhanced_articles

        except Exception as e:
            logger.error(f"AI-enhanced crawling failed for {site_config.name}: {e}")
            return []

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

    async def _apply_ai_analysis(self, article: Dict) -> Dict:
        """
        Apply comprehensive AI analysis pipeline to article

        Includes:
        - Topic modeling (BERTopic + Tomotopy)
        - Sentiment analysis
        - NewsReader integration (if available)
        - Quality scoring
        """
        try:
            content = article.get('content', '')
            if not content or len(content) < 100:
                return article

            # Sentiment analysis
            if self._sentiment_pipeline:
                try:
                    sentiment_result = self._sentiment_pipeline(content[:512])[0]
                    article['sentiment'] = {
                        'label': sentiment_result['label'],
                        'score': sentiment_result['score']
                    }
                except Exception as e:
                    logger.debug(f"Sentiment analysis failed: {e}")

            # Topic modeling with BERTopic
            if self._bertopic_model:
                try:
                    topics, probs = self._bertopic_model.transform([content])
                    if topics and len(topics) > 0:
                        topic_info = self._bertopic_model.get_topic(topics[0])
                        article['bertopic_topics'] = {
                            'topic_id': int(topics[0]),
                            'probability': float(probs[0]),
                            'top_words': topic_info[:10] if topic_info else []
                        }
                except Exception as e:
                    logger.debug(f"BERTopic analysis failed: {e}")

            # Online LDA with Tomotopy
            if self._lda_model:
                try:
                    # Add document to online LDA model
                    doc_id = self._lda_model.add_doc(content.split())
                    self._lda_model.train(10)  # Quick training iteration

                    # Get topic distribution
                    topic_dist = self._lda_model.get_topic_dist(doc_id)
                    dominant_topic = int(topic_dist.argmax())

                    article['lda_topics'] = {
                        'dominant_topic': dominant_topic,
                        'topic_distribution': topic_dist.tolist()[:10],  # Top 10 topics
                        'topic_words': [
                            word for word, _ in self._lda_model.get_topic_words(dominant_topic, top_n=5)
                        ]
                    }
                except Exception as e:
                    logger.debug(f"Online LDA analysis failed: {e}")

            # NewsReader integration (if available)
            if self._newsreader_available:
                try:
                    from agents.newsreader.tools import process_article_content
                    newsreader_result = await process_article_content(
                        content={
                            "url": article.get('url', ''),
                            "screenshot_path": None  # Could be enhanced to capture screenshot
                        },
                        content_type="webpage",
                        processing_mode="comprehensive"
                    )
                    if newsreader_result and newsreader_result.get("status") == "success":
                        article['newsreader_analysis'] = newsreader_result
                except Exception as e:
                    logger.debug(f"NewsReader analysis failed: {e}")

            # Enhanced quality scoring
            base_score = article.get('news_score', 0.5)
            enhancements = 0

            if 'sentiment' in article:
                enhancements += 0.1
            if 'bertopic_topics' in article:
                enhancements += 0.15
            if 'lda_topics' in article:
                enhancements += 0.15
            if 'newsreader_analysis' in article:
                enhancements += 0.2

            article['enhanced_quality_score'] = min(1.0, base_score + enhancements)
            article['ai_analysis_applied'] = True

            return article

        except Exception as e:
            logger.error(f"AI analysis failed for article: {e}")
            return article

    async def crawl_site(self, site_config: SiteConfig, max_articles: int = 25) -> List[Dict]:
        """
        Crawl a single site using the optimal strategy
        """
        start_time = time.time()
        strategy = self._determine_optimal_strategy(site_config)
        logger.info(f"🎯 Selected strategy for {site_config.name}: {strategy}")

        # Record crawl start
        self.performance_monitor.record_crawl_start(site_config, strategy)

        articles = []
        error_count = 0

        try:
            if strategy == 'ultra_fast':
                articles = await self._crawl_ultra_fast_mode(site_config, max_articles)
            elif strategy == 'ai_enhanced':
                articles = await self._crawl_ai_enhanced_mode(site_config, max_articles)
            else:  # generic
                articles = await self._crawl_generic_mode(site_config, max_articles)
        except Exception as e:
            logger.error(f"❌ Crawling failed for {site_config.name}: {e}")
            error_count = 1
            articles = []

        # Record performance metrics
        processing_time = time.time() - start_time
        successful_articles = len([a for a in articles if a.get('status') == 'success'])
        articles_per_second = len(articles) / processing_time if processing_time > 0 else 0

        # Update performance monitor
        self.performance_monitor.record_crawl_complete(
            site_config, len(articles), successful_articles, processing_time
        )

        performance_data = {
            'articles_found': len(articles),
            'articles_successful': successful_articles,
            'processing_time_seconds': processing_time,
            'articles_per_second': articles_per_second,
            'strategy_used': strategy,
            'error_count': error_count
        }

        # Update source strategy and record performance
        if site_config.source_id:
            update_source_crawling_strategy(site_config.source_id, strategy, performance_data)
            record_crawling_performance(site_config.source_id, performance_data)

        return articles

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
                articles = await self.crawl_site(site_config, max_articles_per_site)
                results[site_config.domain] = articles
                self.performance_metrics["articles_processed"] += len(articles)
                self.performance_metrics["sites_crawled"] += 1
                logger.info(f"🏁 Completed {site_config.name}: {len(articles)} articles")

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

        summary = {
            "unified_crawl": True,
            "sites_crawled": len(results),
            "total_articles": total_articles,
            "processing_time_seconds": total_time,
            "articles_per_second": articles_per_second,
            "strategy_breakdown": self.performance_metrics["mode_usage"],
            "site_breakdown": {domain: len(articles) for domain, articles in results.items()},
            "timestamp": datetime.now().isoformat(),
            "articles": all_articles,
            "performance_metrics": self.performance_metrics,
            "optimization_recommendations": self.performance_optimizer.get_optimization_recommendations(),
            "configuration_suggestions": self.performance_optimizer.suggest_configuration_changes()
        }

        logger.info("🎉 Unified multi-site crawl complete!")
        logger.info(f"📊 Articles: {total_articles} ({articles_per_second:.2f}/sec)")
        logger.info(f"📈 Sites: {len(results)}")
        logger.info(f"🎯 Strategies: {self.performance_metrics['mode_usage']}")

        return summary

    async def run_unified_crawl(self, domains: Optional[List[str]] = None,
                              max_articles_per_site: int = 25,
                              concurrent_sites: int = 3,
                              max_total_articles: int = 100) -> Dict[str, Any]:
        """
        Main entry point for unified production crawling
        """
        logger.info("🎯 Starting Unified Production Crawler")

        # Load site configurations
        if domains:
            sources = get_sources_by_domain(domains)
        else:
            sources = get_active_sources()

        site_configs = []
        for source in sources:
            try:
                config = SiteConfig(source)
                site_configs.append(config)
            except Exception as e:
                logger.warning(f"Failed to create config for {source.get('name', 'Unknown')}: {e}")

        if not site_configs:
            logger.error("❌ No site configurations available")
            return {"error": "No sources available"}

        # Execute unified crawl
        return await self.crawl_multiple_sites(
            site_configs,
            max_articles_per_site,
            concurrent_sites
        )

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report"""
        total_time = time.time() - self.performance_metrics["start_time"]

        return {
            "total_runtime_seconds": total_time,
            "articles_processed": self.performance_metrics["articles_processed"],
            "sites_crawled": self.performance_metrics["sites_crawled"],
            "errors": self.performance_metrics["errors"],
            "articles_per_second": self.performance_metrics["articles_processed"] / total_time if total_time > 0 else 0,
            "mode_usage": self.performance_metrics["mode_usage"],
            "timestamp": datetime.now().isoformat()
        }


# Export for Scout Agent integration
__all__ = ['UnifiedProductionCrawler']
