"""
Migrated Database Utilities - MariaDB + ChromaDB Support
Updated utilities for the migrated JustNews database system

Features:
- MariaDB connection and operations
- ChromaDB vector database integration
- Semantic search capabilities
- Backward compatibility with existing code
"""

import asyncio
import os
from importlib import import_module
from typing import Any

from common.observability import get_logger
from database.models.migrated_models import MigratedDatabaseService

logger = get_logger(__name__)


def _get_compat_attr(name: str, default):
    """Retrieve an attribute from the compatibility shim if available."""
    try:
        compat_module = import_module("database.refactor.utils.database_utils")
    except Exception:
        return default

    return getattr(compat_module, name, default)
"""
Migrated Database Utilities - MariaDB + ChromaDB Support
Updated utilities for the migrated JustNews database system

Features:
- MariaDB connection and operations
- ChromaDB vector database integration
- Semantic search capabilities
- Backward compatibility with existing code
"""



from common.observability import get_logger

logger = get_logger(__name__)


def _get_compat_attr(name: str, default):
    """Retrieve an attribute from the compatibility shim if available."""
    try:
        compat_module = import_module("database.refactor.utils.database_utils")
    except Exception:
        return default

    return getattr(compat_module, name, default)


def get_db_config() -> dict[str, Any]:
    """
    Get database configuration from environment and config files

    Returns:
        Database configuration dictionary with MariaDB and ChromaDB settings
    """
    # Resolve paths
    env_file_path = '/etc/justnews/global.env'
    import json
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'system_config.json')

    # Prefer an explicit system_config.json when available (tests mock this path).
    system_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding='utf-8') as f:
                system_config = json.load(f)
        except Exception as e:
            logger.warning(f"Could not open system_config.json at {config_path}: {e}")
            system_config = {}
    else:
        # If system config not present, allow loading a host-level env file
        if os.path.exists(env_file_path):
            logger.info(f"Loading environment variables from {env_file_path}")
            try:
                with open(env_file_path, encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
            except Exception:
                # If global.env exists but fails to read, continue with defaults/env
                logger.warning(f"Failed to read env file at {env_file_path}")

    # Build config from system_config (if any) or defaults
    db_config = system_config.get('database', {}) if isinstance(system_config, dict) else {}

    mariadb_from_config = isinstance(db_config.get('mariadb'), dict)
    chromadb_from_config = isinstance(db_config.get('chromadb'), dict)
    embedding_from_config = isinstance(db_config.get('embedding'), dict)

    # Set default values if not specified (copy to avoid mutating source dicts)
    mariadb_config = dict(db_config.get('mariadb', {
        'host': 'localhost',
        'port': 3306,
        'database': 'justnews',
        'user': 'justnews',
        'password': 'migration_password_2024'
    }))
    chromadb_config = dict(db_config.get('chromadb', {
        'host': 'localhost',
        'port': 8000,
        'collection': 'articles'
    }))

    embedding_config = dict(db_config.get('embedding', {
        'model': 'all-MiniLM-L6-v2',
        'dimensions': 384,
        'device': 'cpu'
    }))

    config = {
        'mariadb': mariadb_config,
        'chromadb': chromadb_config,
        'embedding': embedding_config,
        'connection_pool': {
            'min_connections': 2,
            'max_connections': 10,
            'connection_timeout_seconds': 3.0,
            'command_timeout_seconds': 30.0
        }
    }

    # Allow explicit environment variable overrides for important runtime
    # values. system_config.json may not include chromadb entries (older
    # configs), and we must prefer CHROMADB_* environment variables when
    # present (for example /etc/justnews/global.env used on the host).
    chroma_host = os.environ.get('CHROMADB_HOST')
    chroma_port = os.environ.get('CHROMADB_PORT')
    chroma_collection = os.environ.get('CHROMADB_COLLECTION')

    if chroma_host and (not chromadb_from_config or not chromadb_config.get('host')):
        config['chromadb']['host'] = chroma_host
    if chroma_port and (not chromadb_from_config or not chromadb_config.get('port')):
        try:
            config['chromadb']['port'] = int(chroma_port)
        except Exception:
            logger.warning(f"Invalid CHROMADB_PORT='{chroma_port}', using config value {config['chromadb'].get('port')}")
    if chroma_collection and (not chromadb_from_config or not chromadb_config.get('collection')):
        config['chromadb']['collection'] = chroma_collection

    # Ensure values from system_config.json take precedence when present
    try:
        if db_config and 'chromadb' in db_config:
            # Overwrite with explicit chromadb section values
            config['chromadb'].update(db_config.get('chromadb', {}))
    except Exception:
        pass

    # Allow environment variable overrides for MariaDB and embedding settings
    # so that tests can set MARIADB_* and EMBEDDING_* variables when system
    # config is not available.
    mariadb_host = os.environ.get('MARIADB_HOST')
    mariadb_port = os.environ.get('MARIADB_PORT')
    mariadb_db = os.environ.get('MARIADB_DB')
    mariadb_user = os.environ.get('MARIADB_USER')
    mariadb_password = os.environ.get('MARIADB_PASSWORD')

    if mariadb_host and (not mariadb_from_config or not mariadb_config.get('host')):
        config['mariadb']['host'] = mariadb_host
    if mariadb_port and (not mariadb_from_config or not mariadb_config.get('port')):
        try:
            config['mariadb']['port'] = int(mariadb_port)
        except Exception:
            logger.warning(f"Invalid MARIADB_PORT='{mariadb_port}', using config value {config['mariadb'].get('port')}")
    if mariadb_db and (not mariadb_from_config or not mariadb_config.get('database')):
        config['mariadb']['database'] = mariadb_db
    if mariadb_user and (not mariadb_from_config or not mariadb_config.get('user')):
        config['mariadb']['user'] = mariadb_user
    if mariadb_password and (not mariadb_from_config or not mariadb_config.get('password')):
        config['mariadb']['password'] = mariadb_password

    embedding_model = os.environ.get('EMBEDDING_MODEL')
    embedding_dimensions = os.environ.get('EMBEDDING_DIMENSIONS')
    embedding_device = os.environ.get('EMBEDDING_DEVICE')

    if embedding_model and (not embedding_from_config or not embedding_config.get('model')):
        config['embedding']['model'] = embedding_model
    if embedding_dimensions and (not embedding_from_config or not embedding_config.get('dimensions')):
        try:
            config['embedding']['dimensions'] = int(embedding_dimensions)
        except Exception:
            logger.warning(f"Invalid EMBEDDING_DIMENSIONS='{embedding_dimensions}', using config value {config['embedding'].get('dimensions')}")
    if embedding_device and (not embedding_from_config or not embedding_config.get('device')):
        config['embedding']['device'] = embedding_device

    # Validate required fields
    required_mariadb = ['host', 'database', 'user', 'password']
    missing_mariadb = [field for field in required_mariadb if not config['mariadb'].get(field)]

    if missing_mariadb:
        raise ValueError(f"Missing required MariaDB configuration fields: {missing_mariadb}")

    return config


def create_database_service(config: dict[str, Any] | None = None) -> MigratedDatabaseService:
    """
    Create and initialize the migrated database service

    Args:
        config: Database configuration (uses get_db_config() if not provided)

    Returns:
        Initialized MigratedDatabaseService instance
    """
    if config is None:
        config = get_db_config()

    # Create a full config dict for the service
    full_config = {'database': config}

    service = MigratedDatabaseService(full_config)

    # Test connections
    check_database_connections(service)

    return service


def check_database_connections(service: MigratedDatabaseService) -> bool:
    """
    Check database connections for the migrated service

    Args:
        service: Database service to check

    Returns:
        True if all connections successful
    """
    try:
        # Test MariaDB connection
        cursor = service.mb_conn.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        cursor.close()

        if not result or result[0] != 1:
            logger.error("MariaDB connection test failed - unexpected result")
            return False

        logger.info("MariaDB connection test successful")

        # Test ChromaDB connection
        collections = service.chroma_client.list_collections()
        if service.collection.name not in [c.name for c in collections]:
            logger.error(f"ChromaDB collection '{service.collection.name}' not found")
            return False

        logger.info("ChromaDB connection test successful")

        # Test embedding model
        test_embedding = service.embedding_model.encode("test")
        if len(test_embedding) != 384:
            logger.error(f"Embedding model returned wrong dimensions: {len(test_embedding)}")
            return False

        logger.info("Embedding model test successful")

        return True

    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


async def execute_query_async(
    service: MigratedDatabaseService,
    query: str,
    params: tuple = None,
    fetch: bool = True
) -> list:
    """
    Execute MariaDB query asynchronously

    Args:
        service: Database service
        query: SQL query string
        params: Query parameters
        fetch: Whether to fetch results

    Returns:
        Query results or empty list
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, execute_mariadb_query, service, query, params, fetch
    )


def execute_mariadb_query(
    service: MigratedDatabaseService,
    query: str,
    params: tuple = None,
    fetch: bool = True
) -> list:
    """
    Execute MariaDB query

    Args:
        service: Database service
        query: SQL query string
        params: Query parameters
        fetch: Whether to fetch results

    Returns:
        Query results or empty list
    """
    try:
        cursor = service.mb_conn.cursor()
        cursor.execute(query, params or ())

        if fetch:
            results = cursor.fetchall()
        else:
            results = []
            service.mb_conn.commit()

        cursor.close()
        return results

    except Exception as e:
        logger.error(f"MariaDB query failed: {e}")
        service.mb_conn.rollback()
        return []


def execute_transaction(
    service: MigratedDatabaseService,
    queries: list,
    params_list: list | None = None
) -> bool:
    """
    Execute multiple MariaDB queries in a transaction

    Args:
        service: Database service
        queries: List of SQL queries
        params_list: List of parameter tuples (optional)

    Returns:
        True if transaction successful
    """
    if params_list is None:
        params_list = [None] * len(queries)

    if len(queries) != len(params_list):
        raise ValueError("queries and params_list must have the same length")

    try:
        cursor = service.mb_conn.cursor()

        for query, params in zip(queries, params_list):
            cursor.execute(query, params or ())

        service.mb_conn.commit()
        cursor.close()

        logger.info(f"Transaction executed successfully with {len(queries)} queries")
        return True

    except Exception as e:
        logger.error(f"Transaction failed: {e}")
        service.mb_conn.rollback()
        return False


def get_database_stats(service: MigratedDatabaseService) -> dict[str, Any]:
    """
    Get comprehensive database statistics for migrated system

    Args:
        service: Database service

    Returns:
        Database statistics dictionary
    """
    stats = {
        'mariadb': {},
        'chromadb': {},
        'total_articles': 0,
        'total_sources': 0,
        'total_vectors': 0
    }

    try:
        # MariaDB stats
        cursor = service.mb_conn.cursor()

        # Article count
        cursor.execute("SELECT COUNT(*) FROM articles")
        stats['mariadb']['articles'] = cursor.fetchone()[0]
        stats['total_articles'] = stats['mariadb']['articles']

        # Source count
        cursor.execute("SELECT COUNT(*) FROM sources")
        stats['mariadb']['sources'] = cursor.fetchone()[0]
        stats['total_sources'] = stats['mariadb']['sources']

        # Article-source mappings
        cursor.execute("SELECT COUNT(*) FROM article_source_map")
        stats['mariadb']['mappings'] = cursor.fetchone()[0]

        cursor.close()

        # ChromaDB stats
        stats['chromadb']['vectors'] = service.collection.count()
        stats['total_vectors'] = stats['chromadb']['vectors']

        # Collections
        collections = service.chroma_client.list_collections()
        stats['chromadb']['collections'] = [c.name for c in collections]

    except Exception as e:
        logger.warning(f"Failed to get database stats: {e}")

    return stats


def semantic_search(
    service: MigratedDatabaseService,
    query: str,
    n_results: int = 5
) -> list[dict[str, Any]]:
    """
    Perform semantic search using the migrated database service

    Args:
        service: Database service
        query: Search query
        n_results: Number of results to return

    Returns:
        List of search results with full article data
    """
    return service.semantic_search(query, n_results)


def search_articles_by_text(
    service: MigratedDatabaseService,
    query: str,
    limit: int = 10
) -> list[dict[str, Any]]:
    """
    Search articles by text content

    Args:
        service: Database service
        query: Search query
        limit: Maximum number of results

    Returns:
        List of matching articles
    """
    return service.search_articles_by_text(query, limit)


def get_recent_articles(
    service: MigratedDatabaseService,
    limit: int = 10
) -> list[dict[str, Any]]:
    """
    Get recent articles

    Args:
        service: Database service
        limit: Maximum number of articles to return

    Returns:
        List of recent articles
    """
    return service.get_recent_articles(limit)


def get_articles_by_source(
    service: MigratedDatabaseService,
    source_id: int | str,
    limit: int = 10
) -> list[dict[str, Any]]:
    """
    Get articles by source

    Args:
        service: Database service
        source_id: Source ID
        limit: Maximum number of articles to return

    Returns:
        List of articles from the source
    """
    return service.get_articles_by_source(source_id, limit)
