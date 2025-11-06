from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from prometheus_client import CollectorRegistry

from agents.memory import tools
from common.stage_b_metrics import configure_stage_b_metrics, use_default_stage_b_metrics


class StubEmbeddingModel:
    def __init__(self, value: float = 0.1):
        self.value = value

    def encode(self, _: str):
        # Minimal deterministic embedding output for tests
        return [self.value, self.value + 0.1, self.value + 0.2]


@pytest.fixture(autouse=True)
def training_system_stub(monkeypatch):
    monkeypatch.setitem(sys.modules, "training_system", SimpleNamespace(collect_prediction=lambda **_: None))
    yield
    sys.modules.pop("training_system", None)


@pytest.fixture
def stage_b_metrics():
    registry = CollectorRegistry()
    metrics = configure_stage_b_metrics(registry)
    yield metrics
    use_default_stage_b_metrics()


def _install_db_stubs(monkeypatch):
    stored_rows: list[dict] = []

    class MockCursor:
        def __init__(self):
            self.query = None
            self.params = None
            self._result = None
            self._lastrowid = None

        def execute(self, query: str, params=None):
            self.query = query
            self.params = params or ()
            normalized_q = " ".join(query.split()).lower()

            # Store for fetchone
            if "from articles where url_hash" in normalized_q:
                target = self.params[0]
                for row in stored_rows:
                    if row.get("url_hash") == target:
                        self._result = ((row["id"],),)
                        return
                self._result = None
            elif "from articles where normalized_url" in normalized_q:
                target = self.params[0]
                for row in stored_rows:
                    if row.get("normalized_url") == target:
                        self._result = ((row["id"],),)
                        return
                self._result = None
            elif "select last_insert_id()" in normalized_q:
                # Return the last inserted ID
                if self._lastrowid:
                    self._result = ((self._lastrowid,),)
                else:
                    self._result = ((len(stored_rows),),)
            elif normalized_q.startswith("insert into articles"):
                new_id = len(stored_rows) + 1
                metadata_payload = self.params[20] if len(self.params) > 20 else None
                review_reasons_payload = self.params[16] if len(self.params) > 16 else None
                stored_rows.append(
                    {
                        "id": new_id,
                        "source_url": self.params[0],
                        "normalized_url": self.params[6],
                        "url_hash": self.params[7],
                        "url_hash_algo": self.params[8],
                        "metadata": json.loads(metadata_payload) if metadata_payload else {},
                        "embedding": self.params[22] if len(self.params) > 22 else [],
                        "needs_review": self.params[15] if len(self.params) > 15 else False,
                        "review_reasons": json.loads(review_reasons_payload) if review_reasons_payload else [],
                        "collection_timestamp": self.params[21] if len(self.params) > 21 else None,
                    }
                )
                self._lastrowid = new_id
                self._result = None
            else:
                self._result = None

        def fetchone(self):
            if self._result:
                return self._result[0]
            return None

        @property
        def lastrowid(self):
            return self._lastrowid

        def close(self):
            pass

    class MockDBConnection:
        def cursor(self):
            return MockCursor()

        def commit(self):
            pass

    class MockDBService:
        def __init__(self):
            self.mb_conn = MockDBConnection()
            self.cb_conn = SimpleNamespace(
                get_or_create_collection=lambda name: SimpleNamespace(
                    add=lambda **kwargs: None
                )
            )
            # Track embeddings added to collection
            self._added_embeddings = []
            
            def mock_collection_add(**kwargs):
                # Store the embedding for verification
                if 'embeddings' in kwargs and kwargs['embeddings']:
                    embedding = kwargs['embeddings'][0]
                    article_id = int(kwargs['ids'][0]) if kwargs.get('ids') else len(stored_rows)
                    # Update the stored row with the embedding
                    for row in stored_rows:
                        if row['id'] == article_id:
                            row['embedding'] = embedding
                            break
            
            self.collection = SimpleNamespace(
                add=mock_collection_add
            )
            self.embedding_model = StubEmbeddingModel()

        def close(self):
            pass

    def mock_create_db_service(*args, **kwargs):
        return MockDBService()

    # Patch create_database_service in the tools module
    import database.utils.migrated_database_utils as db_utils
    monkeypatch.setattr(db_utils, "create_database_service", mock_create_db_service)
    monkeypatch.setattr(tools, "log_feedback", lambda *args, **kwargs: None)
    monkeypatch.setattr(tools, "get_embedding_model", lambda: StubEmbeddingModel())

    return stored_rows


def test_save_article_inserts_metadata(monkeypatch, stage_b_metrics):
    stored_rows = _install_db_stubs(monkeypatch)

    metadata = {
        "url": "https://example.com/news?id=123&utm_source=feed",
        "canonical": "https://example.com/news",
        "publisher_meta": {"source": "Example"},
        "language": "en",
        "authors": ["Alex"],
        "tags": ["Politics"],
        "needs_review": True,
        "review_reasons": ["word_count_below_threshold"],
    }

    result = tools.save_article("Sample content for embedding", metadata, embedding_model=StubEmbeddingModel())

    assert result["status"] == "success"
    assert result["article_id"] == 1
    assert len(stored_rows) == 1

    stored = stored_rows[0]
    assert stored["normalized_url"] == "https://example.com/news"
    assert stored["url_hash"]
    assert stored["url_hash_algo"] == "sha256"
    assert stored["needs_review"] is True
    assert stored["review_reasons"] == ["word_count_below_threshold"]
    assert stored["metadata"]["publisher_meta"] == {"source": "Example"}
    assert stored["embedding"] == pytest.approx([0.1, 0.2, 0.3])
    assert stored["collection_timestamp"] is not None
    assert stage_b_metrics.get_ingestion_count("success") == 1.0
    assert stage_b_metrics.get_embedding_count("success") == 1.0
    assert stage_b_metrics.get_embedding_latency_sum("provided") >= 0.0


def test_save_article_detects_duplicates(monkeypatch, stage_b_metrics):
    stored_rows = _install_db_stubs(monkeypatch)

    metadata = {
        "url": "https://example.com/path?a=1",
        "canonical": "https://example.com/path",
    }

    first = tools.save_article("primary", metadata, embedding_model=StubEmbeddingModel())
    second = tools.save_article("secondary", metadata, embedding_model=StubEmbeddingModel())

    assert first["status"] == "success"
    assert second["status"] == "duplicate"
    assert len(stored_rows) == 1
    assert stage_b_metrics.get_ingestion_count("success") == 1.0
    assert stage_b_metrics.get_ingestion_count("duplicate") == 1.0
    assert stage_b_metrics.get_embedding_count("success") == 1.0


def test_save_article_normalizes_on_duplicate_variants(monkeypatch, stage_b_metrics):
    stored_rows = _install_db_stubs(monkeypatch)

    meta_one = {"url": "https://example.com/world/story/?utm_campaign=news", "canonical": None}
    meta_two = {"url": "https://example.com/world/story/#section"}

    first = tools.save_article("content", meta_one, embedding_model=StubEmbeddingModel())
    second = tools.save_article("content", meta_two, embedding_model=StubEmbeddingModel())

    assert first["status"] == "success"
    assert second["status"] == "duplicate"
    assert len(stored_rows) == 1
    assert stored_rows[0]["normalized_url"] == "https://example.com/world/story"
    assert stage_b_metrics.get_ingestion_count("success") == 1.0
    assert stage_b_metrics.get_ingestion_count("duplicate") == 1.0
    assert stage_b_metrics.get_embedding_count("success") == 1.0


def test_save_article_metrics_embedding_model_unavailable(monkeypatch, stage_b_metrics):
    stored_rows = _install_db_stubs(monkeypatch)
    monkeypatch.setattr(tools, "get_embedding_model", lambda: None)

    result = tools.save_article(
        "content",
        {"url": "https://example.com/missing"},
        embedding_model=None,
    )

    assert result["error"] == "embedding_model_unavailable"
    assert stage_b_metrics.get_ingestion_count("embedding_model_unavailable") == 1.0
    assert len(stored_rows) == 0
    assert stage_b_metrics.get_embedding_count("model_unavailable") == 1.0
