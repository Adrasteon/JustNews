"""
Tools and utilities for the Crawler Control Agent.
"""
from typing import List

from agents.common.database import execute_query


def get_sources_with_limit(limit: int = None) -> List[str]:
    """Get active sources from database, optionally limited"""
    try:
        query = """
            SELECT domain
            FROM public.sources
            WHERE last_verified IS NOT NULL
            AND last_verified > now() - interval '30 days'
            ORDER BY last_verified DESC, name ASC
        """
        if limit:
            query += f" LIMIT {limit}"

        sources = execute_query(query)
        domains = [source['domain'] for source in sources]
        return domains

    except Exception as e:
        from common.observability import get_logger
        logger = get_logger(__name__)
        logger.error(f"❌ Failed to query sources from database: {e}")
        return []