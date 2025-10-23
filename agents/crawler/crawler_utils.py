#!/usr/bin/env python3
"""
Shared Crawler Utilities for JustNewsAgent Production Crawlers

PHASE 2 UPDATE: Added database-driven source management with PostgreSQL integration
and connection pooling for scalable multi-site crawling operations.

Consolidated utilities for:
- Rate limiting across domains
- Robots.txt compliance checking
- Modal and cookie consent dismissal
- Canonical metadata generation
- Database source management with connection pooling
- Common crawler patterns

Used by all production crawler implementations to ensure consistency and
support database-driven multi-site clustering operations.
"""

import asyncio
import hashlib
import json

# Database utilities for source management
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from common.observability import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Unified rate limiter for production crawlers"""

    def __init__(self, requests_per_minute: int = 20, delay_between_requests: float = 2.0):
        self.requests_per_minute = requests_per_minute
        self.delay_between_requests = delay_between_requests
        self.domain_requests = defaultdict(list)  # Track requests per domain
        self.last_request_time = 0

    async def wait_if_needed(self, domain: str):
        """Wait if rate limits would be exceeded"""
        current_time = time.time()

        # Global rate limiting
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.delay_between_requests:
            await asyncio.sleep(self.delay_between_requests - time_since_last_request)

        # Domain-specific rate limiting
        domain_requests = self.domain_requests[domain]
        # Remove requests older than 1 minute
        domain_requests[:] = [req_time for req_time in domain_requests if current_time - req_time < 60]

        if len(domain_requests) >= self.requests_per_minute:
            # Wait until we can make another request
            oldest_request = min(domain_requests)
            wait_time = 60 - (current_time - oldest_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        # Record this request
        self.domain_requests[domain].append(current_time)
        self.last_request_time = time.time()


class RobotsChecker:
    """Unified robots.txt compliance checker with caching"""

    def __init__(self):
        self.robots_cache = {}  # Cache robots.txt parsing results
        self.user_agent = 'JustNewsAgent/1.0'

    def check_robots_txt(self, url: str) -> bool:
        """Check if crawling is allowed by robots.txt for the given URL"""
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            robots_url = f"https://{domain}/robots.txt"

            # Check cache first
            if domain in self.robots_cache:
                rp, last_check = self.robots_cache[domain]
                # Cache for 1 hour
                if time.time() - last_check < 3600:
                    return rp.can_fetch(self.user_agent, url)

            # Fetch and parse robots.txt
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                self.robots_cache[domain] = (rp, time.time())
                return rp.can_fetch(self.user_agent, url)
            except Exception:
                # If robots.txt can't be fetched, assume crawling is allowed
                logger.warning(f"Could not fetch robots.txt for {domain}, assuming allowed")
                return True

        except Exception as e:
            logger.warning(f"Error checking robots.txt for {url}: {e}")
            return True  # Default to allowed if check fails


class ModalDismisser:
    """Unified modal and cookie consent dismissal"""

    @staticmethod
    async def dismiss_modals(page):
        """Dismiss all common modals, overlays, and cookie consent dialogs"""

        # Cookie consent - most common patterns
        cookie_selectors = [
            'button:has-text("Accept")',
            'button:has-text("I Agree")',
            'button:has-text("Continue")',
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            '[data-testid="accept-all"]',
            '[id*="accept"]',
            '[id*="cookie"]',
            '.fc-cta-consent',  # OneTrust
            '.banner-actions-button',  # Common BBC pattern
        ]

        # Sign-in and other modals
        dismiss_selectors = [
            'button:has-text("Not now")',
            'button:has-text("Skip")',
            'button:has-text("Maybe later")',
            'button:has-text("Continue without")',
            'button:has-text("No thanks")',
            '[aria-label="Dismiss"]',
            '[aria-label="Close"]',
            '[aria-label="close"]',
            'button[aria-label*="close"]',
            '.close-button',
            '.modal-close',
            '[data-testid="close"]',
            '[data-testid="dismiss"]',
        ]

        all_selectors = cookie_selectors + dismiss_selectors

        # Try all selectors quickly
        for selector in all_selectors:
            try:
                elements = page.locator(selector)
                count = await elements.count()
                if count > 0:
                    await elements.first.click(timeout=1000)
                    await asyncio.sleep(0.5)  # Brief pause
                    logger.debug(f"Dismissed modal: {selector}")
            except Exception:
                continue  # Ignore failures, keep trying


class CanonicalMetadata:
    """Unified canonical metadata generation for all crawlers"""

    @staticmethod
    def generate_metadata(url: str, title: str = "", content: str = "",
                         extraction_method: str = "unknown", status: str = "success",
                         paywall_flag: bool = False, confidence: float = 0.0,
                         publisher: str = "BBC", crawl_mode: str = "ultra_fast",
                         news_score: float = 0.0, canonical: str | None = None,
                         error: str | None = None) -> dict:
        """Generate standardized canonical metadata for crawler results"""

        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        domain = urlparse(url).netloc

        metadata = {
            "url": url,
            "url_hash": url_hash,
            "domain": domain,
            "canonical": canonical,
            "title": title,
            "content": content,
            "extraction_method": extraction_method,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "paywall_flag": paywall_flag,
            "confidence": confidence,
            "publisher_meta": {"publisher": publisher},
            "crawl_mode": crawl_mode,
            "news_score": news_score,
            "extraction_metadata": {}
        }

        if error:
            metadata["error"] = error
            metadata["extraction_metadata"]["error"] = error

        return metadata

    @staticmethod
    async def extract_canonical_and_paywall(page) -> tuple[str | None, bool]:
        """Extract canonical URL and detect paywall from page"""
        canonical = None
        paywall_flag = False

        try:
            # Extract canonical link
            canonical = await page.evaluate("""
                () => {
                    const c = document.querySelector('link[rel="canonical"]');
                    return c ? c.href : null;
                }
            """)
        except Exception:
            canonical = None

        try:
            # Check for paywall indicators
            paywall_selectors = ['.paywall', '.subscription-required', '.member-only', '[data-paywall]']
            for sel in paywall_selectors:
                try:
                    if await page.locator(sel).count() > 0:
                        paywall_flag = True
                        break
                except Exception:
                    continue

            # Also check content for paywall keywords
            if not paywall_flag:
                title = await page.title()
                body_text = await page.locator('body').text_content()
                content = (title + ' ' + body_text).lower()
                paywall_keywords = ['subscribe', 'subscription', 'member', 'sign in', 'log in', 'paywall']
                if any(keyword in content for keyword in paywall_keywords):
                    paywall_flag = True
        except Exception:
            paywall_flag = False

        return canonical, paywall_flag


# Global instances for shared use
rate_limiter = RateLimiter()
robots_checker = RobotsChecker()

# Environment variables
POSTGRES_HOST = os.environ.get("POSTGRES_HOST")
POSTGRES_DB = os.environ.get("POSTGRES_DB")
POSTGRES_USER = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")

# Connection pool configuration
POOL_MIN_CONNECTIONS = int(os.environ.get("DB_POOL_MIN_CONNECTIONS", "2"))
POOL_MAX_CONNECTIONS = int(os.environ.get("DB_POOL_MAX_CONNECTIONS", "10"))

# Global connection pool
_connection_pool: pool.ThreadedConnectionPool | None = None

def initialize_connection_pool():
    """
    Initialize the PostgreSQL connection pool.
    Should be called once at application startup.
    """
    global _connection_pool
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    if _connection_pool is not None:
        return _connection_pool

    try:
        # Dynamic env refresh: if any core value is missing, attempt to resolve from alternates
        if not all([POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD]):
            prev = (POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)
            POSTGRES_HOST = (
                POSTGRES_HOST
                or os.environ.get("JUSTNEWS_DB_HOST")
                or os.environ.get("DB_HOST")
                or "localhost"
            )
            POSTGRES_DB = (
                POSTGRES_DB
                or os.environ.get("JUSTNEWS_DB_NAME")
                or os.environ.get("DB_NAME")
                or os.environ.get("POSTGRES_DB")
                or "justnews"
            )
            POSTGRES_USER = (
                POSTGRES_USER
                or os.environ.get("JUSTNEWS_DB_USER")
                or os.environ.get("DB_USER")
                or os.environ.get("POSTGRES_USER")
                or "justnews_user"
            )
            POSTGRES_PASSWORD = (
                POSTGRES_PASSWORD
                or os.environ.get("JUSTNEWS_DB_PASSWORD")
                or os.environ.get("DB_PASSWORD")
                or os.environ.get("POSTGRES_PASSWORD")
                or "password123"
            )
            if prev != (POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD):
                logger.warning(
                    "🔄 Refreshed DB env values dynamically host=%s db=%s user=%s (password=****)",
                    POSTGRES_HOST,
                    POSTGRES_DB,
                    POSTGRES_USER,
                )

        _connection_pool = pool.ThreadedConnectionPool(
            minconn=POOL_MIN_CONNECTIONS,
            maxconn=POOL_MAX_CONNECTIONS,
            host=POSTGRES_HOST,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            connect_timeout=3,
            options='-c search_path=public'
        )
        logger.info(f"✅ Database connection pool initialized with {POOL_MIN_CONNECTIONS}-{POOL_MAX_CONNECTIONS} connections")
        return _connection_pool
    except Exception as e:
        logger.error(f"❌ Failed to initialize database connection pool: {e}")
        raise

@contextmanager
def get_db_connection():
    """Context manager for getting a database connection from the pool"""
    global _connection_pool

    if _connection_pool is None:
        initialize_connection_pool()

    conn = None
    try:
        conn = _connection_pool.getconn()
        yield conn
    finally:
        if conn:
            _connection_pool.putconn(conn)

def execute_query(query: str, params: tuple = None) -> list[dict[str, Any]]:
    """Execute a query and return results as list of dicts"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            return [dict(row) for row in cur.fetchall()]

def execute_query_single(query: str, params: tuple = None) -> dict[str, Any] | None:
    """Execute a query and return a single result as dict"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return dict(row) if row else None

def get_active_sources() -> list[dict[str, Any]]:
    """Get all active news sources from the database"""
    try:
        sources = execute_query("""
            SELECT id, url, domain, name, description, metadata,
                   last_verified, created_at, updated_at
            FROM public.sources
            WHERE last_verified IS NOT NULL
            AND last_verified > now() - interval '30 days'
            ORDER BY last_verified DESC, name ASC
        """)

        logger.info(f"✅ Found {len(sources)} active sources in database")
        return sources

    except Exception as e:
        logger.error(f"❌ Failed to query sources from database: {e}")
        return []

def get_sources_by_domain(domains: list[str]) -> list[dict[str, Any]]:
    """Get sources for specific domains"""
    if not domains:
        return []

    try:
        placeholders = ','.join(['%s'] * len(domains))
        query = f"""
            SELECT id, url, domain, name, description, metadata,
                   last_verified, created_at, updated_at
            FROM public.sources
            WHERE domain IN ({placeholders})
            AND last_verified IS NOT NULL
            ORDER BY last_verified DESC
        """

        sources = execute_query(query, tuple(domains))
        logger.info(f"✅ Found {len(sources)} sources for domains: {domains}")
        return sources

    except Exception as e:
        logger.warning(f"⚠️ Failed to query sources by domain (continuing without database): {e}")
        return []

def update_source_crawling_strategy(source_id: int, strategy: str, performance_data: dict) -> bool:
    """Update source with crawling strategy and performance data"""
    try:
        # Update metadata with crawling strategy
        metadata_update = {
            "crawling_strategy": strategy,
            "last_crawling_performance": performance_data,
            "last_crawling_attempt": datetime.now().isoformat()
        }

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.sources
                    SET metadata = metadata || %s,
                        last_verified = now(),
                        updated_at = now()
                    WHERE id = %s
                """, (json.dumps(metadata_update), source_id))

                if cur.rowcount > 0:
                    conn.commit()  # CRITICAL: Commit the transaction
                    logger.info(f"✅ Updated crawling strategy for source {source_id}: {strategy}")
                    return True
                else:
                    logger.warning(f"⚠️ No source found with ID {source_id}")
                    return False

    except Exception as e:
        logger.error(f"❌ Failed to update source crawling strategy: {e}")
        return False

def get_sources_with_strategy() -> list[dict[str, Any]]:
    """Get sources with their assigned crawling strategies"""
    try:
        sources = execute_query("""
            SELECT id, url, domain, name, description, metadata,
                   last_verified, created_at, updated_at
            FROM public.sources
            WHERE last_verified IS NOT NULL
            AND last_verified > now() - interval '30 days'
            AND metadata ? 'crawling_strategy'
            ORDER BY last_verified DESC, name ASC
        """)

        logger.info(f"✅ Found {len(sources)} sources with crawling strategies")
        return sources

    except Exception as e:
        logger.error(f"❌ Failed to query sources with strategies: {e}")
        return []

def record_crawling_performance(source_id: int, performance_data: dict) -> bool:
    """Record crawling performance metrics for a source"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.crawling_performance
                    (source_id, articles_found, articles_successful, processing_time_seconds,
                     articles_per_second, strategy_used, error_count, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                """, (
                    source_id,
                    performance_data.get('articles_found', 0),
                    performance_data.get('articles_successful', 0),
                    performance_data.get('processing_time_seconds', 0.0),
                    performance_data.get('articles_per_second', 0.0),
                    performance_data.get('strategy_used', 'unknown'),
                    performance_data.get('error_count', 0)
                ))

                conn.commit()  # CRITICAL: Commit the transaction
                logger.info(f"✅ Recorded performance for source {source_id}")
                return True

    except Exception as e:
        logger.warning(f"⚠️ Failed to record crawling performance (continuing without performance tracking): {e}")
        return False

def get_source_performance_history(source_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """Get performance history for a source"""
    try:
        performance = execute_query("""
            SELECT articles_found, articles_successful, processing_time_seconds,
                   articles_per_second, strategy_used, error_count, timestamp
            FROM public.crawling_performance
            WHERE source_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (source_id, limit))

        logger.info(f"✅ Found {len(performance)} performance records for source {source_id}")
        return performance

    except Exception as e:
        logger.warning(f"⚠️ Failed to get performance history (continuing without performance data): {e}")
        return []

def get_optimal_sources_for_strategy(strategy: str, limit: int = 10) -> list[dict[str, Any]]:
    """Get sources that perform best with a specific crawling strategy"""
    try:
        sources = execute_query("""
            SELECT s.id, s.url, s.domain, s.name, s.description,
                   AVG(cp.articles_per_second) as avg_performance,
                   COUNT(cp.*) as crawl_count,
                   MAX(cp.timestamp) as last_crawl
            FROM public.sources s
            JOIN public.crawling_performance cp ON s.id = cp.source_id
            WHERE cp.strategy_used = %s
            AND cp.timestamp > now() - interval '7 days'
            GROUP BY s.id, s.url, s.domain, s.name, s.description
            HAVING COUNT(cp.*) >= 3
            ORDER BY AVG(cp.articles_per_second) DESC
            LIMIT %s
        """, (strategy, limit))

        logger.info(f"✅ Found {len(sources)} optimal sources for {strategy} strategy")
        return sources

    except Exception as e:
        logger.error(f"❌ Failed to get optimal sources for strategy: {e}")
        return []

def create_crawling_performance_table() -> bool:
    """Create the crawling performance tracking table if it doesn't exist"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS public.crawling_performance (
                        id SERIAL PRIMARY KEY,
                        source_id INTEGER REFERENCES public.sources(id),
                        articles_found INTEGER NOT NULL DEFAULT 0,
                        articles_successful INTEGER NOT NULL DEFAULT 0,
                        processing_time_seconds FLOAT NOT NULL DEFAULT 0.0,
                        articles_per_second FLOAT NOT NULL DEFAULT 0.0,
                        strategy_used VARCHAR(50) NOT NULL,
                        error_count INTEGER NOT NULL DEFAULT 0,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT now()
                    );

                    CREATE INDEX IF NOT EXISTS idx_crawling_performance_source_id
                    ON public.crawling_performance(source_id);

                    CREATE INDEX IF NOT EXISTS idx_crawling_performance_timestamp
                    ON public.crawling_performance(timestamp);

                    CREATE INDEX IF NOT EXISTS idx_crawling_performance_strategy
                    ON public.crawling_performance(strategy_used);
                """)

                conn.commit()  # CRITICAL: Commit the transaction
                logger.info("✅ Crawling performance table created/verified")
                return True

    except Exception as e:
        logger.error(f"❌ Failed to create crawling performance table: {e}")
        return False
