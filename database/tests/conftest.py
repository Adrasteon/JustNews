# Database Refactor Tests - Configuration and Fixtures

import pytest
import os
from unittest.mock import Mock, patch
from database.core.connection_pool import DatabaseConnectionPool
from database.core.schema_manager import SchemaManager
from database.core.migration_engine import MigrationEngine
from database.core.query_optimizer import QueryOptimizer
from database.core.backup_manager import BackupManager
from database.models.base_model import BaseModel
from database.utils.database_utils import get_db_config


@pytest.fixture
def mock_db_config():
    """Mock database configuration for testing"""
    return {
        'host': 'localhost',
        'port': 5432,
        'database': 'test_db',
        'user': 'test_user',
        'password': 'test_password',
        'min_connections': 1,
        'max_connections': 5,
        'health_check_interval': 30,
        'max_retries': 3,
        'retry_delay': 1.0
    }


@pytest.fixture
def mock_connection():
    """Mock database connection"""
    conn = Mock()
    conn.cursor.return_value.__enter__ = Mock()
    conn.cursor.return_value.__exit__ = Mock()
    conn.close = Mock()
    return conn


@pytest.fixture
def mock_pool(mock_db_config):
    """Mock connection pool"""
    with patch('psycopg2.connect') as mock_connect:
        from database.core.connection_pool import DatabaseConnectionPool
        pool = DatabaseConnectionPool(mock_db_config)
        # Mock the pool attribute to avoid actual database connections
        pool.pool = Mock()
        pool.pool.getconn = Mock(return_value=Mock())
        pool.pool.putconn = Mock()
        pool.pool.closeall = Mock()
        pool.pool._pool = []
        pool.pool._used = []
        
        # Mock the execute_query method
        pool.execute_query = Mock()
        
        # Mock the get_metrics method
        pool.get_metrics = Mock(return_value={'connections_created': 5})
        
        # Mock the get_connection method to return a context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=Mock())
        mock_context.__exit__ = Mock(return_value=None)
        pool.get_connection = Mock(return_value=mock_context)
        
        yield pool


@pytest.fixture
def mock_schema_manager(mock_pool):
    """Mock schema manager"""
    return SchemaManager(mock_pool)


@pytest.fixture
def mock_migration_engine(mock_pool):
    """Mock migration engine"""
    return MigrationEngine(mock_pool)


@pytest.fixture
def mock_query_optimizer(mock_pool):
    """Mock query optimizer"""
    return QueryOptimizer(mock_pool)


@pytest.fixture
def mock_backup_manager(mock_pool):
    """Mock backup manager"""
    backup_config = {
        'backup_dir': '/tmp/test_backups',
        'storage_backends': []
    }
    return BackupManager(mock_pool, backup_config)


@pytest.fixture
def mock_base_model(mock_pool):
    """Mock base model setup"""
    BaseModel.set_connection_pool(mock_pool)
    yield BaseModel
    # Reset after test
    BaseModel._connection_pool = None


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables for testing"""
    env_vars = {
        'POSTGRES_HOST': 'localhost',
        'POSTGRES_PORT': '5432',
        'POSTGRES_DB': 'test_db',
        'POSTGRES_USER': 'test_user',
        'POSTGRES_PASSWORD': 'test_password',
        'DB_MIN_CONNECTIONS': '1',
        'DB_MAX_CONNECTIONS': '5',
        'DB_HEALTH_CHECK_INTERVAL': '30',
        'DB_MAX_RETRIES': '3',
        'DB_RETRY_DELAY': '1.0'
    }

    with patch.dict(os.environ, env_vars):
        yield


@pytest.fixture
def test_db_config():
    """Get test database configuration"""
    return get_db_config()