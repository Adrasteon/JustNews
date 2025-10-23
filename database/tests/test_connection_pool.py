# Database Refactor Tests - Connection Pool Tests

import pytest
from unittest.mock import Mock, patch, call
from database.refactor.core.connection_pool import DatabaseConnectionPool


class TestDatabaseConnectionPool:
    """Test cases for DatabaseConnectionPool"""

    def test_init_with_config(self, mock_db_config):
        """Test initialization with configuration dictionary"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool(mock_db_config)

            assert pool.config == mock_db_config
            assert pool.min_connections == mock_db_config['min_connections']
            assert pool.max_connections == mock_db_config['max_connections']
            assert pool.pool is not None  # Check that pool was created

    def test_init_with_env_vars(self, mock_env_vars):
        """Test initialization using environment variables"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool()

            assert pool.config['host'] == 'localhost'
            assert pool.config['port'] == 5432
            assert pool.config['database'] == 'test_db'

    def test_get_connection_success(self, mock_db_config):
        """Test successful connection retrieval"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool(mock_db_config)
            
            # Mock the pool methods
            pool.pool = Mock()
            pool.pool.getconn.return_value = Mock()
            pool.pool.putconn = Mock()
            
            with pool.get_connection() as conn:
                assert conn is not None

            # Verify connection was returned to pool
            pool.pool.putconn.assert_called_once()

    def test_get_connection_pool_exhausted(self, mock_db_config):
        """Test behavior when pool is exhausted"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool(mock_db_config)
            
            # Mock the pool to be exhausted
            pool.pool = Mock()
            pool.pool.getconn.side_effect = Exception("Pool exhausted")

            with patch.object(pool, '_get_healthy_connection', return_value=Mock()) as mock_get_conn:
                with pool.get_connection() as conn:
                    assert conn is not None

                mock_get_conn.assert_called_once()

    def test_health_check_success(self, mock_connection):
        """Test successful health check"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool({'host': 'localhost', 'port': 5432, 'database': 'test', 'user': 'test', 'password': 'test', 'min_connections': 1, 'max_connections': 5, 'health_check_interval': 30, 'max_retries': 3, 'retry_delay': 1.0})
            
            mock_connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)

            result = pool._health_check(mock_connection)
            assert result is True

    def test_health_check_failure(self, mock_connection):
        """Test failed health check"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool({'host': 'localhost', 'port': 5432, 'database': 'test', 'user': 'test', 'password': 'test', 'min_connections': 1, 'max_connections': 5, 'health_check_interval': 30, 'max_retries': 3, 'retry_delay': 1.0})
            
            mock_connection.cursor.side_effect = Exception("Connection failed")

            result = pool._health_check(mock_connection)
            assert result is False

    def test_failover_to_backup_pool(self, mock_db_config):
        """Test failover to backup pool"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool(mock_db_config)
            
            # Mock pools
            pool.pool = Mock()
            pool.pool.getconn.side_effect = Exception("Primary failed")
            
            # Mock backup pool
            backup_pool_mock = Mock()
            backup_pool_mock.getconn.return_value = Mock()
            pool.backup_pools = [backup_pool_mock]

            with pool.get_connection() as conn:
                assert conn is not None

            backup_pool_mock.getconn.assert_called_once()

    def test_get_metrics(self, mock_db_config):
        """Test metrics collection"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool(mock_db_config)
            
            # Set some metrics
            pool.metrics['connections_created'] = 5
            pool.metrics['connections_acquired'] = 10
            pool.metrics['connections_released'] = 10

            metrics = pool.get_metrics()

            assert metrics['connections_created'] == 5
            assert metrics['connections_acquired'] == 10
            assert metrics['connections_released'] == 10
            assert 'total_connections' in metrics
            assert 'is_healthy' in metrics

    def test_close_all_connections(self, mock_db_config):
        """Test closing all connections"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool(mock_db_config)
            
            # Mock the pool
            pool.pool = Mock()
            pool.pool.closeall = Mock()

            pool.close()

            # Verify closeall was called on the main pool
            pool.pool.closeall.assert_called_once()

    def test_context_manager(self, mock_db_config):
        """Test context manager behavior"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool(mock_db_config)
            
            # Mock the pool
            pool.pool = Mock()
            pool.pool.closeall = Mock()

            with pool as pool_obj:
                assert pool_obj is pool

            # Verify close was called
            pool.pool.closeall.assert_called_once()

    def test_connection_health_check(self, mock_db_config):
        """Test connection health check functionality"""
        with patch('psycopg2.connect') as mock_connect:
            pool = DatabaseConnectionPool(mock_db_config)
            
            # Mock successful health check
            with patch.object(pool, '_perform_health_check', return_value=True):
                pool._perform_health_check()
                assert pool.is_healthy is True