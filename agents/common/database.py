"""
Database connection utilities for JustNewsAgent
Provides connection pooling and async database operations
"""

import os
from contextlib import contextmanager

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from common.observability import get_logger
from common.dev_db_fallback import apply_test_db_env_fallback

# Configure centralized logging
logger = get_logger(__name__)

# Environment variables (read at runtime, not import time)
def get_db_config():
    """Get database configuration from environment variables"""
    # Load global.env file first
    env_file_path = '/etc/justnews/global.env'
    if os.path.exists(env_file_path):
        logger.info(f"Loading environment variables from {env_file_path}")
        with open(env_file_path) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

    # Apply development fallback credentials if required
    applied = apply_test_db_env_fallback(logger)
    if applied:
        logger.warning("Development DB fallback variables applied: %s", ",".join(applied))

    # Then try individual POSTGRES_* variables
    config = {
        'host': os.environ.get("POSTGRES_HOST"),
        'database': os.environ.get("POSTGRES_DB"),
        'user': os.environ.get("POSTGRES_USER"),
        'password': os.environ.get("POSTGRES_PASSWORD")
    }
    
    # If any are missing, try to parse DATABASE_URL
    if not all(config.values()):
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            logger.info("Parsing database configuration from DATABASE_URL")
            try:
                from urllib.parse import urlparse
                parsed = urlparse(database_url)
                config['host'] = parsed.hostname or config['host']
                config['database'] = parsed.path.lstrip('/') or config['database']
                config['user'] = parsed.username or config['user']
                config['password'] = parsed.password or config['password']
                if parsed.port:
                    config['port'] = parsed.port
            except Exception as e:
                logger.warning(f"Failed to parse DATABASE_URL: {e}")
    
    return config

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

    if _connection_pool is not None:
        return _connection_pool

    try:
        # Add debug prints to log resolved database configuration
        config = get_db_config()
        logger.debug(f"Resolved database configuration: {config}")

        _connection_pool = pool.ThreadedConnectionPool(
            minconn=POOL_MIN_CONNECTIONS,
            maxconn=POOL_MAX_CONNECTIONS,
            host=config['host'],
            database=config['database'],
            user=config['user'],
            password=config['password'],
            connect_timeout=3,
            options='-c search_path=public'
        )
        logger.info(f"✅ Database connection pool initialized with {POOL_MIN_CONNECTIONS}-{POOL_MAX_CONNECTIONS} connections")
        return _connection_pool
    except Exception as e:
        logger.error(f"❌ Failed to initialize connection pool: {e}")
        raise

def get_connection_pool():
    """
    Get the global connection pool instance.
    Initializes it if not already done.
    """
    if _connection_pool is None:
        return initialize_connection_pool()
    return _connection_pool

@contextmanager
def get_db_connection():
    """
    Context manager for getting a database connection from the pool.
    Automatically returns the connection to the pool when done.
    """
    pool = get_connection_pool()
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            pool.putconn(conn)

@contextmanager
def get_db_cursor(commit: bool = False):
    """
    Context manager for getting a database cursor with connection.
    Automatically handles connection pooling and optional commit.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            logger.debug("Acquired database cursor.")
            yield conn, cursor
            if commit:
                conn.commit()
                logger.debug("Transaction committed.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Database operation error: {e}")
            raise
        finally:
            cursor.close()
            logger.debug("Database cursor closed.")

def execute_query(query: str, params: tuple = None, fetch: bool = True) -> list | None:
    """
    Execute a database query with automatic connection management.

    Args:
        query: SQL query string
        params: Query parameters
        fetch: Whether to fetch results (for SELECT queries)

    Returns:
        List of results if fetch=True and it's a SELECT query, None otherwise
    """
    with get_db_cursor(commit=True) as (conn, cursor):
        cursor.execute(query, params or ())
        if fetch and query.strip().upper().startswith('SELECT'):
            return cursor.fetchall()
        return None

def execute_query_single(query: str, params: tuple = None) -> dict | None:
    """
    Execute a query and return a single result row.

    Args:
        query: SQL query string
        params: Query parameters

    Returns:
        Single result row as dict, or None if no results
    """
    with get_db_cursor() as (conn, cursor):
        cursor.execute(query, params or ())
        result = cursor.fetchone()
        return dict(result) if result else None

def health_check() -> bool:
    """
    Perform a database health check.

    Returns:
        True if database is healthy, False otherwise
    """
    try:
        result = execute_query_single("SELECT 1 as health_check")
        return result is not None and result.get('health_check') == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

def get_pool_stats() -> dict:
    """
    Get connection pool statistics.

    Returns:
        Dictionary with pool statistics
    """
    pool = get_connection_pool()
    return {
        "min_connections": POOL_MIN_CONNECTIONS,
        "max_connections": POOL_MAX_CONNECTIONS,
        "connections_in_use": len(pool._used),
        "connections_available": len(pool._rused) - len(pool._used),
        "total_connections": len(pool._rused)
    }

# Cleanup function for graceful shutdown
def close_connection_pool():
    """Close all connections in the pool. Call during application shutdown."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        logger.info("Database connection pool closed")
        _connection_pool = None
