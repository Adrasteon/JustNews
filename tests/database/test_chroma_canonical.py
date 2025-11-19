import os
import pytest

from database.utils.migrated_database_utils import get_db_config, create_database_service
from database.utils.chromadb_utils import ChromaCanonicalValidationError


def test_chroma_canonical_enforcement(tmp_path, monkeypatch):
    # Set a mismatched CHROMADB host/port while canonical expects a different port
    monkeypatch.setenv('CHROMADB_REQUIRE_CANONICAL', '1')
    monkeypatch.setenv('CHROMADB_CANONICAL_HOST', 'localhost')
    monkeypatch.setenv('CHROMADB_CANONICAL_PORT', '3307')
    monkeypatch.setenv('CHROMADB_HOST', 'localhost')
    monkeypatch.setenv('CHROMADB_PORT', '8000')

    # Provide a fake MariaDB connection to avoid the top-level test harness's
    # 'mysql.connector.connect' replacement that raises by default. The test
    # only needs a minimal connection to reach the Chroma validation logic.
    from unittest.mock import MagicMock, patch
    with patch('mysql.connector.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [1]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Because the canonical host/port mismatch is fatal, create_database_service should raise
        with pytest.raises(ChromaCanonicalValidationError):
            create_database_service()
