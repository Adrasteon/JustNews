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

    # Because the canonical host/port mismatch is fatal, create_database_service should raise
    with pytest.raises(ChromaCanonicalValidationError):
        create_database_service()
