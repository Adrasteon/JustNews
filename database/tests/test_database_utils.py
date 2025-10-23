# Database Refactor Tests - Database Utilities Tests

import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
from database.refactor.utils.database_utils import (
    get_db_config, create_connection_pool, execute_query_async,
    execute_transaction, get_database_stats, vacuum_analyze_table,
    reindex_table, get_slow_queries, kill_query, check_connection
)


class TestDatabaseUtils:
    """Test cases for database utilities"""

    def test_get_db_config_from_env(self, mock_env_vars):
        """Test getting database config from environment variables"""
        config = get_db_config()

        assert config['host'] == 'localhost'
        assert config['port'] == 5432
        assert config['database'] == 'test_db'
        assert config['user'] == 'test_user'
        assert config['password'] == 'test_password'

    def test_get_db_config_from_url(self):
        """Test getting database config from DATABASE_URL"""
        with patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@host:5432/db'}):
            config = get_db_config()

            assert config['host'] == 'host'
            assert config['port'] == 5432
            assert config['database'] == 'db'
            assert config['user'] == 'user'
            assert config['password'] == 'pass'

    def test_create_connection_pool(self, mock_db_config):
        """Test creating connection pool"""
        with patch('database.refactor.utils.database_utils.DatabaseConnectionPool') as mock_pool_class, \
             patch('database.refactor.utils.database_utils.check_connection') as mock_check_conn:
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool
            mock_check_conn.return_value = True

            pool = create_connection_pool(mock_db_config)

            mock_pool_class.assert_called_once_with(mock_db_config)
            mock_check_conn.assert_called_once_with(mock_pool)
            assert pool == mock_pool

    @pytest.mark.asyncio
    async def test_execute_query_async(self, mock_pool):
        """Test asynchronous query execution"""
        mock_pool.execute_query.return_value = [{'result': 'test'}]

        result = await execute_query_async(mock_pool, "SELECT 1", (1,))

        mock_pool.execute_query.assert_called_once_with("SELECT 1", (1,), True)
        assert result == [{'result': 'test'}]

    def test_execute_transaction_success(self, mock_pool):
        """Test successful transaction execution"""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        
        # Set up the mock context manager
        mock_context = mock_pool.get_connection.return_value
        mock_context.__enter__.return_value = mock_conn

        queries = ["INSERT INTO test VALUES (1)", "UPDATE test SET name = 'test'"]
        params_list = [(1,), ('test',)]

        result = execute_transaction(mock_pool, queries, params_list)

        assert result is True
        assert mock_cursor.execute.call_count == 2
        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()

    def test_execute_transaction_rollback(self, mock_pool):
        """Test transaction rollback on error"""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = Exception("Query failed")
        mock_conn.cursor.return_value = mock_cursor
        
        # Set up the mock context manager
        mock_context = mock_pool.get_connection.return_value
        mock_context.__enter__.return_value = mock_conn

        queries = ["INSERT INTO test VALUES (1)"]
        params_list = [(1,)]

        result = execute_transaction(mock_pool, queries, params_list)

        assert result is False

    def test_get_database_stats(self, mock_pool):
        """Test getting database statistics"""
        mock_pool.execute_query.side_effect = [
            [{'tablename': 'test_table', 'inserts': 10, 'updates': 5, 'deletes': 2, 'live_rows': 100, 'dead_rows': 5, 'size': '1 MB'}],
            [{'db_size': '10 MB'}]
        ]
        mock_pool.get_metrics.return_value = {'connections_created': 5}

        stats = get_database_stats(mock_pool)

        assert 'connection_pool' in stats
        assert 'tables' in stats
        assert stats['tables']['test_table']['live_rows'] == 100

    def test_vacuum_analyze_table(self, mock_pool):
        """Test VACUUM ANALYZE operation"""
        mock_pool.execute_query.return_value = None

        result = vacuum_analyze_table(mock_pool, "test_table")

        assert result is True
        mock_pool.execute_query.assert_called_once_with("VACUUM ANALYZE test_table", fetch=False)

    def test_reindex_table(self, mock_pool):
        """Test REINDEX operation"""
        mock_pool.execute_query.return_value = None

        result = reindex_table(mock_pool, "test_table")

        assert result is True
        mock_pool.execute_query.assert_called_once_with("REINDEX TABLE test_table", fetch=False)

    def test_get_slow_queries(self, mock_pool):
        """Test getting slow queries"""
        mock_pool.execute_query.return_value = [
            {'pid': 123, 'usename': 'test_user', 'query_preview': 'SELECT * FROM large_table', 'duration': 15.5}
        ]

        slow_queries = get_slow_queries(mock_pool, limit=5, min_duration=10.0)

        assert len(slow_queries) == 1
        assert slow_queries[0]['pid'] == 123
        mock_pool.execute_query.assert_called_once()

    def test_kill_query(self, mock_pool):
        """Test killing a query"""
        mock_pool.execute_query.return_value = [{'pg_terminate_backend': True}]

        result = kill_query(mock_pool, 12345)

        assert result is True
        mock_pool.execute_query.assert_called_once_with("SELECT pg_terminate_backend(%s)", (12345,))

    def test_check_connection_success(self, mock_pool):
        """Test successful connection check"""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = [1]
        mock_conn.cursor.return_value = mock_cursor
        
        # Set up the mock context manager
        mock_context = mock_pool.get_connection.return_value
        mock_context.__enter__.return_value = mock_conn

        result = check_connection(mock_pool)

        assert result is True
        mock_cursor.execute.assert_called_once_with("SELECT 1 as test")
        mock_cursor.close.assert_called_once()

    def test_check_connection_failure(self, mock_pool):
        """Test failed connection check"""
        # Set up the mock context manager to raise an exception
        mock_context = mock_pool.get_connection.return_value
        mock_context.__enter__.side_effect = Exception("Connection failed")

        result = check_connection(mock_pool)

        assert result is False