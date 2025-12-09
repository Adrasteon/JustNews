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
import json
import os
from importlib import import_module
from typing import Any

from common.observability import get_logger
from database.models.migrated_models import MigratedDatabaseService

logger = get_logger(__name__)

# Cache a single MigratedDatabaseService instance for this process
_cached_service: MigratedDatabaseService | None = None


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


def get_db_config() -> dict[str, Any]:
    """
    Get database configuration from environment and config files

    Returns:
        Database configuration dictionary with MariaDB and ChromaDB settings
    """
    # Resolve paths
    env_file_paths = [
        '/etc/justnews/global.env',  # System-wide location
        os.path.join(os.path.dirname(__file__), '..', '..', 'global.env'),  # Workspace root
    ]
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'system_config.json')

    # Always try to load environment variables from global.env files first
    for env_file_path in env_file_paths:
        if os.path.exists(env_file_path):
            logger.info(f"Loading environment variables from {env_file_path}")
            try:
                with open(env_file_path, encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                # Do not overwrite process environment variables that may
                                # be set by tests or higher-priority runtime configuration.
                                k = key.strip()
                                if os.environ.get(k) is None:
                                    os.environ[k] = value.strip()
                break  # Load from first available file
            except Exception:
                # If global.env exists but fails to read, continue with defaults/env
                logger.warning(f"Failed to read env file at {env_file_path}")
    
    # Prefer an explicit system_config.json when available (tests mock this path).
    system_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding='utf-8') as f:
                system_config = json.load(f)
        except Exception as e:
            logger.warning(f"Could not open system_config.json at {config_path}: {e}")
            system_config = {}

    # Build config from system_config (if any) or defaults
    db_config = system_config.get('database', {}) if isinstance(system_config, dict) else {}

    embedding_from_config = isinstance(db_config.get('embedding'), dict)

    # Set default values if not specified (copy to avoid mutating source dicts)
    file_mariadb_config = db_config.get('mariadb', {}) if isinstance(db_config.get('mariadb'), dict) else {}
    file_chromadb_config = db_config.get('chromadb', {}) if isinstance(db_config.get('chromadb'), dict) else {}

    mariadb_config = dict(file_mariadb_config or {
        'host': 'localhost',
        'port': 3306,
        'database': 'justnews',
        'user': 'justnews',
        'password': 'migration_password_2024'
    })
    chromadb_config = dict(file_chromadb_config or {
        'host': 'localhost',
        'port': 3307,
        'collection': 'articles'
    })
    # Tenant support (Chroma 0.4+ managed servers may have tenants)
    chromadb_tenant = db_config.get('chromadb', {}).get('tenant') or os.environ.get('CHROMADB_TENANT')
    if chromadb_tenant:
        chromadb_config['tenant'] = chromadb_tenant

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
    # Canonical Chromadb host/port environment (optional)
    config['chromadb_canonical'] = {
        'host': os.environ.get('CHROMADB_CANONICAL_HOST'),
        'port': os.environ.get('CHROMADB_CANONICAL_PORT')
    }

    # Allow explicit environment variable overrides for important runtime
    # values. system_config.json may not include chromadb entries (older
    # configs), and we must prefer CHROMADB_* environment variables when
    # present (for example /etc/justnews/global.env used on the host).
    chroma_host = os.environ.get('CHROMADB_HOST')
    chroma_port = os.environ.get('CHROMADB_PORT')
    chroma_collection = os.environ.get('CHROMADB_COLLECTION')

    def _has_config_value(section: dict[str, Any], key: str) -> bool:
        if not isinstance(section, dict):
            return False
        value = section.get(key)
        return value not in (None, "", [])

    # Environment variables should override system_config.json values when provided
    if chroma_host and not _has_config_value(file_chromadb_config, 'host'):
        config['chromadb']['host'] = chroma_host
    if chroma_port and not _has_config_value(file_chromadb_config, 'port'):
        try:
            config['chromadb']['port'] = int(chroma_port)
        except Exception:
            logger.warning(f"Invalid CHROMADB_PORT='{chroma_port}', using config value {config['chromadb'].get('port')}")
    if chroma_collection and not _has_config_value(file_chromadb_config, 'collection'):
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

    if mariadb_host and not _has_config_value(file_mariadb_config, 'host'):
        config['mariadb']['host'] = mariadb_host
    if mariadb_port and not _has_config_value(file_mariadb_config, 'port'):
        try:
            config['mariadb']['port'] = int(mariadb_port)
        except Exception:
            logger.warning(f"Invalid MARIADB_PORT='{mariadb_port}', using config value {config['mariadb'].get('port')}")
    if mariadb_db and not _has_config_value(file_mariadb_config, 'database'):
        config['mariadb']['database'] = mariadb_db
    if mariadb_user and not _has_config_value(file_mariadb_config, 'user'):
        config['mariadb']['user'] = mariadb_user
    if mariadb_password is not None and not _has_config_value(file_mariadb_config, 'password'):
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
    missing_mariadb = [field for field in required_mariadb if field not in config['mariadb']]

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
    global _cached_service
    if config is None:
        config = get_db_config()

    # Return cached instance if the config and relevant env flags are identical
    try:
        if _cached_service is not None:
            # Compare the cached configuration and the CHROMADB_MODEL_SCOPED_COLLECTION
            # flag used when the service was created. This prevents reusing a cached
            # service that was created with a different collection scoping behaviour
            # (model-scoped vs canonical) which would result in embeddings being
            # written to a different Chroma collection than expected.
            current_scoped = os.environ.get('CHROMADB_MODEL_SCOPED_COLLECTION', '0')
            cached_scoped = getattr(_cached_service, '_chroma_scoped_env', None)
            if config and getattr(_cached_service, 'config', None) == {'database': config} and cached_scoped == current_scoped:
                return _cached_service
    except Exception:
        # If comparing configs fails for any reason, ignore and recreate service
        pass

    # If canonical enforcement is enabled, validate the configured chroma host/port
    # against the canonical host/port and fail early when they don't match.
    try:
        require_canonical = os.environ.get('CHROMADB_REQUIRE_CANONICAL', '0') == '1'
        if require_canonical:
            canonical = config.get('chromadb_canonical', {}) if config else {}
            canon_host = canonical.get('host')
            canon_port = canonical.get('port')
            # Only attempt strict validation when canonical host/port are provided
            if canon_host and canon_port:
                from database.utils.chromadb_utils import validate_chroma_is_canonical

                # raise_on_fail=True will raise ChromaCanonicalValidationError on mismatch
                validate_chroma_is_canonical(
                    config['chromadb'].get('host'),
                    config['chromadb'].get('port'),
                    canon_host,
                    int(canon_port),
                    raise_on_fail=True,
                )
    except Exception:
        # Let the caller handle any validation error (tests expect a raised exception)
        raise

    # Create a full config dict for the service
    full_config = {'database': config}

    service = MigratedDatabaseService(full_config)
    # Record the CHROMADB_MODEL_SCOPED_COLLECTION env value that led to this
    # service initialization so subsequent calls can validate compatibility
    try:
        service._chroma_scoped_env = os.environ.get('CHROMADB_MODEL_SCOPED_COLLECTION', '0')
    except Exception:
        service._chroma_scoped_env = '0'

    # Test connections
    check_database_connections(service)

    # Cache the service so subsequent calls reuse the same Chroma/MariaDB connections
    _cached_service = service
    return service


def close_cached_service():
    """Close and clear the cached database service if present."""
    global _cached_service
    if _cached_service:
        try:
            _cached_service.close()
        except Exception:
            pass
    _cached_service = None


def check_database_connections(service: MigratedDatabaseService) -> bool:
    """
    Check database connections for the migrated service

    Args:
        service: Database service to check

    Returns:
        True if all connections successful
    """
    try:
        # Test MariaDB connection using a safe per-call cursor so health checks
        # don't compete with live queries on the shared connection.
        cursor, conn = service.get_safe_cursor(per_call=True, buffered=True)
        try:
            cursor.execute("SELECT 1 as test")
            result = cursor.fetchone()
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

        if not result or result[0] != 1:
            logger.error("MariaDB connection test failed - unexpected result")
            return False

        logger.info("MariaDB connection test successful")

        # Test ChromaDB connection - optional
        try:
            if service.chroma_client and service.collection:
                collections = service.chroma_client.list_collections()
                if service.collection.name not in [c.name for c in collections]:
                    logger.error(f"ChromaDB collection '{service.collection.name}' not found")
                    return False
                logger.info("ChromaDB connection test successful")
            else:
                logger.warning("ChromaDB client or collection not available - skipping ChromaDB checks")
        except Exception as e:
            logger.warning(f"ChromaDB check failed (continuing without chroma): {e}")

        # Test embedding model if available. The database service will run
        # degraded if SentenceTransformer is not present (embedding_model=None).
        if getattr(service, 'embedding_model', None) is None:
            # Embeddings are optional for many agents and in CI/dev the
            # SentenceTransformer may be unavailable. Log and continue.
            logger.warning("Embedding model not available - skipping embedding test")
        else:
            try:
                test_embedding = service.embedding_model.encode("test")
                if len(test_embedding) != 384:
                    logger.error(f"Embedding model returned wrong dimensions: {len(test_embedding)}")
                    return False
                logger.info("Embedding model test successful")
            except Exception as e:
                logger.warning(f"Embedding model test failed (continuing): {e}")

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
        # Use a per-call connection for queries to avoid sharing resultsets
        # across concurrent callers which can produce 'Unread result found'.
        conn = None
        cursor = None
        try:
            # create per-call connection+cursor
            cursor, conn = service.get_safe_cursor(per_call=True, buffered=True, dictionary=False)
            cursor.execute(query, params or ())
            if fetch:
                results = cursor.fetchall()
            else:
                results = []
                conn.commit()
            return results
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

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
        # For transactions we must use a single per-call connection so the
        # statements are executed on the same connection and can be committed
        # together.
        conn = service.get_connection()
        cursor = conn.cursor()
        try:
            for query, params in zip(queries, params_list, strict=True):
                cursor.execute(query, params or ())

            conn.commit()
            logger.info(f"Transaction executed successfully with {len(queries)} queries")
            return True
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

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
        # Use per-call connection for stats so we don't interfere with live
        # queries on the shared connection.
        cursor, conn = service.get_safe_cursor(per_call=True, buffered=True)
        try:
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
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

        # ChromaDB stats
        if getattr(service, 'collection', None):
            try:
                stats['chromadb']['vectors'] = service.collection.count()
            except Exception as e:
                logger.warning(f"Failed to count ChromaDB vectors: {e}")
                stats['chromadb']['vectors'] = 0
        else:
            stats['chromadb']['vectors'] = 0
        stats['total_vectors'] = stats['chromadb']['vectors']

        # Collections
        try:
            if getattr(service, 'chroma_client', None):
                collections = service.chroma_client.list_collections()
                stats['chromadb']['collections'] = [c.name for c in collections]
            else:
                stats['chromadb']['collections'] = []
        except Exception as e:
            logger.warning(f"Failed retrieving ChromaDB collections: {e}")
            stats['chromadb']['collections'] = []

    except Exception as e:
        logger.warning(f"Failed to get database stats: {e}")

    return stats


## Knowledge Graph helpers (DB-backed)


def add_entity(service: MigratedDatabaseService, name: str, entity_type: str, confidence: float | None = None, canonical_name: str | None = None, detection_source: str | None = None) -> int | None:
    """Add or find an entity in the DB-backed entities table.

    Returns the entity id on success, or None on error.
    """
    try:
        service.ensure_conn()
        cursor = service.mb_conn.cursor()
        # Check existing
        if canonical_name:
            cursor.execute("SELECT id FROM entities WHERE (name=%s AND entity_type=%s) OR (canonical_name=%s AND entity_type=%s) LIMIT 1", (name, entity_type, canonical_name, entity_type))
        else:
            cursor.execute("SELECT id FROM entities WHERE name=%s AND entity_type=%s LIMIT 1", (name, entity_type))
        row = cursor.fetchone()
        if row:
            eid = row[0]
            cursor.close()
            return eid

        cursor.execute("INSERT INTO entities (name, entity_type, confidence_score, canonical_name, detection_source) VALUES (%s,%s,%s,%s,%s)", (name, entity_type, confidence, canonical_name, detection_source))
        service.mb_conn.commit()
        cursor.execute("SELECT LAST_INSERT_ID()")
        lid = cursor.fetchone()
        cursor.close()
        return lid[0] if lid else None
    except Exception as e:
        logger.warning(f"add_entity failed: {e}")
        try:
            service.mb_conn.rollback()
        except Exception:
            pass
        return None


def link_entity_to_article(service: MigratedDatabaseService, article_id: int, entity_id: int, relevance: float | None = None) -> bool:
    """Link an entity to an article in the article_entities junction table."""
    try:
        service.ensure_conn()
        cursor = service.mb_conn.cursor()
        cursor.execute("INSERT IGNORE INTO article_entities (article_id, entity_id, relevance_score) VALUES (%s,%s,%s)", (article_id, entity_id, relevance))
        service.mb_conn.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.warning(f"link_entity_to_article failed: {e}")
        try:
            service.mb_conn.rollback()
        except Exception:
            pass
        return False


def log_kg_operation(service: MigratedDatabaseService, operation: str, actor: str | None = None, target_type: str | None = None, target_id: int | None = None, details: dict | None = None) -> bool:
    """Write a KG audit event to kg_audit table (and fallback to file log).

    operation: one of create_entity, link_entity, read_entities, search_entities, etc.
    """
    payload = details or {}
    try:
        if service:
            service.ensure_conn()
            cursor = service.mb_conn.cursor()
            cursor.execute("INSERT INTO kg_audit (operation, actor, target_type, target_id, details) VALUES (%s,%s,%s,%s,%s)", (operation, actor, target_type, target_id, json.dumps(payload)))
            service.mb_conn.commit()
            cursor.close()
            return True
    except Exception as e:
        logger.warning(f"kg_audit DB insert failed: {e}")

    # Fallback - append to logs/audit/kg_operations.jsonl
    try:
        log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'audit')
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, 'kg_operations.jsonl')
        entry = {'operation': operation, 'actor': actor, 'target_type': target_type, 'target_id': target_id, 'details': payload}
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, default=str) + '\n')
        return True
    except Exception as e:
        logger.warning(f"kg_audit file fallback failed: {e}")
        return False


def get_article_entities(service: MigratedDatabaseService, article_id: int) -> list[dict[str, Any]]:
    """Return list of entity dicts attached to an article."""
    try:
        service.ensure_conn()
        cursor = service.mb_conn.cursor()
        cursor.execute(
            "SELECT e.id, e.name, e.entity_type, e.confidence_score, e.canonical_name, e.detection_source, ae.relevance_score FROM entities e JOIN article_entities ae ON e.id = ae.entity_id WHERE ae.article_id = %s",
            (article_id,)
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {"id": r[0], "name": r[1], "entity_type": r[2], "confidence_score": float(r[3]) if r[3] is not None else None, "canonical_name": r[4], "detection_source": r[5], "relevance": float(r[6]) if r[6] is not None else None}
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"get_article_entities failed: {e}")
        return []


def search_entities(service: MigratedDatabaseService, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search entities by name prefix or substring."""
    try:
        service.ensure_conn()
        cursor = service.mb_conn.cursor()
        pattern = f"%{query}%"
        cursor.execute("SELECT id, name, entity_type, confidence_score, canonical_name, detection_source FROM entities WHERE name LIKE %s OR entity_type LIKE %s LIMIT %s", (pattern, pattern, limit))
        rows = cursor.fetchall()
        cursor.close()
        return [{"id": r[0], "name": r[1], "entity_type": r[2], "confidence_score": float(r[3]) if r[3] is not None else None, "canonical_name": r[4], "detection_source": r[5]} for r in rows]
    except Exception as e:
        logger.warning(f"search_entities failed: {e}")
        return []


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
