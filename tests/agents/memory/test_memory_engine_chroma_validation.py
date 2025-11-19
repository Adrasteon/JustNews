import pytest
import asyncio

from agents.memory.memory_engine import MemoryEngine


def test_memory_engine_init_fails_on_chroma_validation(monkeypatch):
    from database.utils.chromadb_utils import ChromaCanonicalValidationError

    def fake_create_db_service():
        raise ChromaCanonicalValidationError('canonical mismatch')

    monkeypatch.setattr('database.utils.migrated_database_utils.create_database_service', fake_create_db_service)

    m = MemoryEngine()
    with pytest.raises(Exception):
        asyncio.get_event_loop().run_until_complete(m.initialize())
