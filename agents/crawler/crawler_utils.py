"""Utility helpers for the simplified crawler stack.

The original system relied on a deep graph of database and browser utilities
that were removed during the repository clean-up.  This lightweight module
reintroduces the minimal surface area required by ``crawler_engine`` so the
service can boot and perform basic work.  Database calls are best-effort: when
PostgreSQL is unavailable the helpers fall back to safe defaults and emit
structured log messages rather than raising fatal exceptions.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from psycopg2 import pool

from common.observability import get_logger

logger = get_logger(__name__)

_POOL_LOCK = threading.Lock()
_CONNECTION_POOL: Optional[pool.SimpleConnectionPool] = None


def _pg_dsn() -> Dict[str, Any]:
    return {
        "host": os.environ.get("postgres_host", "localhost"),
        "port": int(os.environ.get("postgres_port", "5432")),
        "dbname": os.environ.get("postgres_db", "justnews"),
        "user": os.environ.get("postgres_user", "justnews_user"),
        "password": os.environ.get("postgres_password", ""),
        "connect_timeout": int(os.environ.get("postgres_connect_timeout", "5")),
    }


def initialize_connection_pool(minconn: int | None = None, maxconn: int | None = None) -> None:
    """Initialise a thread-safe psycopg2 connection pool."""
    global _CONNECTION_POOL
    if _CONNECTION_POOL:
        return
    with _POOL_LOCK:
        if _CONNECTION_POOL:
            return
        min_conn = minconn or int(os.environ.get("db_pool_min_connections", "1"))
        max_conn = maxconn or int(os.environ.get("db_pool_max_connections", "4"))
        try:
            _CONNECTION_POOL = pool.SimpleConnectionPool(min_conn, max_conn, **_pg_dsn())
            logger.info("Created PostgreSQL connection pool (%s-%s)", min_conn, max_conn)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create PostgreSQL connection pool: %s", exc)
            _CONNECTION_POOL = None


@contextmanager
def _get_conn():
    conn = None
    try:
        if _CONNECTION_POOL:
            conn = _CONNECTION_POOL.getconn()
        else:
            conn = psycopg2.connect(**_pg_dsn())
        yield conn
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database operation failed: %s", exc)
        raise
    finally:
        if conn is not None:
            if _CONNECTION_POOL:
                _CONNECTION_POOL.putconn(conn)
            else:
                conn.close()


def create_crawling_performance_table() -> None:
    """Ensure the crawler performance table exists (no-op on failure)."""
    ddl = """
    CREATE TABLE IF NOT EXISTS crawler_performance (
        id SERIAL PRIMARY KEY,
        source_id BIGINT,
        domain TEXT,
        strategy_used TEXT,
        articles_processed INT,
        articles_per_second REAL,
        duration_seconds REAL,
        crawled_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
                conn.commit()
    except Exception:
        logger.debug("Skipping crawler_performance table creation (database unavailable)")


@dataclass
class CanonicalMetadata:
    """Reusable structure for canonical article hints."""

    url: str
    title: Optional[str] = None
    published_at: Optional[datetime] = None


class RateLimiter:
    """Simple token bucket per domain to prevent hammering a site."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def acquire(self, domain: str) -> None:
        with self._lock:
            bucket = self._records.setdefault(domain, deque())
            now = time.monotonic()
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                sleep_for = self.window_seconds - (now - bucket[0])
                logger.debug("Rate limiter sleeping %.2fs for %s", sleep_for, domain)
                time.sleep(max(0.0, sleep_for))
            bucket.append(time.monotonic())


class RobotsChecker:
    """Very light robots.txt checker; currently permissive."""

    def is_allowed(self, url: str) -> bool:
        return True


class ModalDismisser:
    """Placeholder for modal-handling logic used by Playwright crawlers."""

    async def dismiss(self, page: Any) -> None:  # pragma: no cover - async placeholder
        return


def _row_to_dict(row: psycopg2.extras.DictRow) -> Dict[str, Any]:
    return dict(row)


def get_active_sources(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM sources ORDER BY last_verified DESC NULLS LAST"
    params: Tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT %s"
        params = (limit,)
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return [_row_to_dict(row) for row in rows]
    except Exception:
        logger.debug("Falling back to empty active sources list")
        return []


def get_sources_by_domain(domains: Iterable[str]) -> List[Dict[str, Any]]:
    domain_list = [d.lower() for d in domains if d]
    if not domain_list:
        return []
    sql = "SELECT * FROM sources WHERE LOWER(domain) = ANY(%s)"
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql, (domain_list,))
                rows = cur.fetchall()
                return [_row_to_dict(row) for row in rows]
    except Exception:
        logger.debug("Could not fetch sources for domains: %s", domain_list)
        return []


def update_source_crawling_strategy(source_id: int, strategy: str) -> None:
    sql = (
        "UPDATE sources SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('crawling_strategy', %s),"
        " updated_at = NOW() WHERE id = %s"
    )
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (strategy, source_id))
                conn.commit()
    except Exception:
        logger.debug("Failed to persist crawling strategy for source_id=%s", source_id)


def record_crawling_performance(
    *,
    source_id: Optional[int],
    domain: Optional[str],
    strategy_used: str,
    articles_processed: int,
    duration_seconds: float,
) -> None:
    if duration_seconds <= 0:
        duration_seconds = 1e-6
    articles_per_second = articles_processed / duration_seconds
    sql = (
        "INSERT INTO crawler_performance (source_id, domain, strategy_used, articles_processed, articles_per_second, duration_seconds)"
        " VALUES (%s, %s, %s, %s, %s, %s)"
    )
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (source_id, domain, strategy_used, articles_processed, articles_per_second, duration_seconds))
                conn.commit()
    except Exception:
        logger.debug("Could not record crawling performance for %s", domain or source_id)


def get_source_performance_history(identifier: Any, limit: int = 5) -> List[Dict[str, Any]]:
    if identifier is None:
        return []
    if isinstance(identifier, int):
        where_clause = "source_id = %s"
        params: Tuple[Any, ...] = (identifier,)
    else:
        where_clause = "LOWER(domain) = %s"
        params = (str(identifier).lower(),)
    sql = (
        f"SELECT source_id, domain, strategy_used, articles_processed, articles_per_second, duration_seconds, crawled_at "
        f"FROM crawler_performance WHERE {where_clause} ORDER BY crawled_at DESC LIMIT %s"
    )
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql, params + (limit,))
                rows = cur.fetchall()
                return [_row_to_dict(row) for row in rows]
    except Exception:
        logger.debug("No performance history found for %s", identifier)
        return []


def get_optimal_sources_for_strategy(strategy: str, limit: int = 10) -> List[Dict[str, Any]]:
    sql = (
        "SELECT source_id, domain, AVG(articles_per_second) AS avg_speed"
        " FROM crawler_performance WHERE strategy_used = %s"
        " GROUP BY source_id, domain ORDER BY avg_speed DESC NULLS LAST LIMIT %s"
    )
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql, (strategy, limit))
                rows = cur.fetchall()
                return [_row_to_dict(row) for row in rows]
    except Exception:
        logger.debug("No optimal sources available for strategy %s", strategy)
        return []


__all__ = [
    "CanonicalMetadata",
    "ModalDismisser",
    "RateLimiter",
    "RobotsChecker",
    "create_crawling_performance_table",
    "get_active_sources",
    "get_optimal_sources_for_strategy",
    "get_source_performance_history",
    "get_sources_by_domain",
    "initialize_connection_pool",
    "record_crawling_performance",
    "update_source_crawling_strategy",
]
