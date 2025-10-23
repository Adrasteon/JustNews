"""
Async database operations for JustNewsAgent
Provides async database operations using asyncpg for non-blocking operations
"""

import os
from contextlib import asynccontextmanager
from typing import Any

from common.observability import get_logger

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None
    ASYNCPG_AVAILABLE = False

logger = get_logger(__name__)

# Environment variables
POSTGRES_HOST = os.environ.get("POSTGRES_HOST")
POSTGRES_DB = os.environ.get("POSTGRES_DB")
POSTGRES_USER = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")

# Global async connection pool
_async_pool: Any | None = None

async def initialize_async_pool():
    """
    Initialize the async PostgreSQL connection pool.
    Should be called once at application startup.
    """
    global _async_pool

    if not ASYNCPG_AVAILABLE:
        raise ImportError("asyncpg is not installed. Install with: pip install asyncpg")

    if _async_pool is not None:
        return _async_pool

    try:
        _async_pool = await asyncpg.create_pool(
            host=POSTGRES_HOST,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            min_size=2,
            max_size=10,
            command_timeout=60,
            init=lambda conn: conn.execute("SET search_path TO public")
        )
        logger.info("✅ Async database connection pool initialized")
        return _async_pool
    except Exception as e:
        logger.error(f"❌ Failed to initialize async connection pool: {e}")
        raise

async def get_async_pool():
    """
    Get the global async connection pool instance.
    Initializes it if not already done.
    """
    if _async_pool is None:
        return await initialize_async_pool()
    return _async_pool

@asynccontextmanager
async def get_async_connection():
    """
    Context manager for getting an async database connection from the pool.
    Automatically returns the connection to the pool when done.
    """
    pool = await get_async_pool()
    conn = await pool.acquire()
    try:
        yield conn
    finally:
        await pool.release(conn)

async def execute_async_query(query: str, *args, fetch: bool = True) -> list[dict[str, Any]] | None:
    """
    Execute an async database query.

    Args:
        query: SQL query string
        *args: Query parameters
        fetch: Whether to fetch results

    Returns:
        List of result rows if fetch=True, None otherwise
    """
    async with get_async_connection() as conn:
        if fetch:
            return await conn.fetch(query, *args)
        else:
            await conn.execute(query, *args)
            return None

async def execute_async_query_single(query: str, *args) -> dict[str, Any] | None:
    """
    Execute a query and return a single result row.

    Args:
        query: SQL query string
        *args: Query parameters

    Returns:
        Single result row as dict, or None if no results
    """
    async with get_async_connection() as conn:
        result = await conn.fetchrow(query, *args)
        return dict(result) if result else None

async def async_health_check() -> bool:
    """
    Perform an async database health check.

    Returns:
        True if database is healthy, False otherwise
    """
    try:
        result = await execute_async_query_single("SELECT 1 as health_check")
        return result is not None and result.get('health_check') == 1
    except Exception as e:
        logger.error(f"Async database health check failed: {e}")
        return False

async def save_article_async(content: str, metadata: dict[str, Any], embedding: list[float]) -> dict[str, Any]:
    """
    Async version of save_article for high-throughput scenarios.

    Args:
        content: Article text content
        metadata: Article metadata
        embedding: Pre-computed embedding vector

    Returns:
        Result dictionary with status and article_id
    """
    try:
        import json

        # Ensure metadata is JSON serializable
        metadata_payload = json.dumps(metadata) if metadata is not None else json.dumps({})

        # Get next available ID
        next_id_result = await execute_async_query_single("SELECT COALESCE(MAX(id), 0) + 1 FROM articles")
        next_id = next_id_result['coalesce'] if next_id_result else 1

        # Insert article
        await execute_async_query(
            "INSERT INTO articles (id, content, metadata, embedding) VALUES ($1, $2, $3::jsonb, $4)",
            next_id, content, metadata_payload, embedding,
            fetch=False
        )

        return {"status": "success", "article_id": next_id, "id": next_id}
    except Exception as e:
        logger.error(f"Error saving article async: {e}")
        return {"error": str(e)}

async def vector_search_async(query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    """
    Async vector search using pre-computed query embedding.

    Args:
        query_embedding: Pre-computed embedding vector for the query
        top_k: Number of top results to return

    Returns:
        List of search results with id, score, content, and metadata
    """
    try:
        # Get all articles with embeddings
        rows = await execute_async_query(
            "SELECT id, content, metadata, embedding FROM articles WHERE embedding IS NOT NULL"
        )

        if not rows:
            return []

        # Compute similarities (simplified - in production you'd use pgvector or similar)
        import numpy as np

        query_emb = np.array(query_embedding, dtype=float)
        results = []

        for row in rows:
            if row['embedding']:
                article_emb = np.array(row['embedding'], dtype=float)
                # Cosine similarity
                similarity = np.dot(query_emb, article_emb) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(article_emb)
                )
                results.append({
                    "id": row['id'],
                    "score": float(similarity),
                    "content": row['content'],
                    "metadata": dict(row['metadata']) if row['metadata'] else None
                })

        # Sort by similarity and return top_k
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    except Exception as e:
        logger.error(f"Error in async vector search: {e}")
        return []

async def close_async_pool():
    """Close all connections in the async pool. Call during application shutdown."""
    global _async_pool
    if _async_pool:
        await _async_pool.close()
        logger.info("Async database connection pool closed")
        _async_pool = None
