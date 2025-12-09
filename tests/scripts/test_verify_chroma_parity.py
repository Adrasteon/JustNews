import json
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


def _make_db_cursor(rows):
    class C:
        def __init__(self):
            self._rows = rows

        def execute(self, q, params=None):
            return None

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def close(self):
            return None

    return C()


def _make_db_service(rows):
    class Conn:
        def __init__(self):
            self._cursor = _make_db_cursor(rows)

        def cursor(self):
            return self._cursor

        def close(self):
            return None

    class Svc:
        def get_connection(self):
            return Conn()

        def ensure_conn(self):
            return None

    return Svc()


@patch("common.stage_b_metrics.get_stage_b_metrics")
@patch("chromadb.HttpClient")
@patch("database.utils.migrated_database_utils.create_database_service")
def test_parity_ok_returns_zero(mock_db_create, mock_chroma_client, mock_get_metrics):
    # MariaDB has one article id=1
    mock_db_create.return_value = _make_db_service([(1, "norm", "hash")])

    # Chroma returns the collection and one document matching
    fake_client = MagicMock()
    fake_client.list_collections.return_value = [SimpleNamespace(name="articles")]
    fake_coll = MagicMock()
    fake_coll.count.return_value = 1
    fake_coll.get.return_value = {"ids": ["1"], "metadatas": [{"normalized_url": "norm", "url_hash": "hash"}], "documents": ["x"]}
    fake_client.get_collection.return_value = fake_coll
    mock_chroma_client.return_value = fake_client

    import scripts.dev.verify_chroma_parity as vcp

    rc = vcp.main([])
    assert rc == 0
    # metrics.record_parity_check should have been called with 'ok'
    mock_get_metrics.return_value.record_parity_check.assert_called_once_with("ok")


@patch("common.stage_b_metrics.get_stage_b_metrics")
@patch("chromadb.HttpClient")
@patch("database.utils.migrated_database_utils.create_database_service")
def test_repair_dry_run_requires_confirm(mock_db_create, mock_chroma_client, mock_get_metrics):
    # DB has article 1, Chroma empty
    mock_db_create.return_value = _make_db_service([(1, "norm", "hash")])

    fake_client = MagicMock()
    fake_client.list_collections.return_value = [SimpleNamespace(name="articles")]
    fake_coll = MagicMock()
    fake_coll.count.return_value = 0
    fake_coll.get.return_value = {"ids": [], "metadatas": [], "documents": []}
    fake_client.get_collection.return_value = fake_coll
    mock_chroma_client.return_value = fake_client

    import scripts.dev.verify_chroma_parity as vcp

    # --repair but no --confirm should perform dry-run and exit code 2 (parity mismatch)
    rc = vcp.main(["--repair"])
    assert rc == 2
    mock_get_metrics.return_value.record_parity_check.assert_called_once_with("mismatch")
    mock_get_metrics.return_value.record_parity_repair.assert_called_once_with("dry_run")


@patch("common.stage_b_metrics.get_stage_b_metrics")
@patch("chromadb.HttpClient")
@patch("database.utils.migrated_database_utils.create_database_service")
def test_repair_confirm_upserts_missing(mock_db_create, mock_chroma_client, mock_get_metrics):
    # DB has article 1 with content & metadata
    rows = [(1, "the content here", json.dumps({"title": "t", "normalized_url": "norm", "url_hash": "hash"}), "norm", "hash", "t")]
    mock_db_create.return_value = _make_db_service(rows)

    fake_client = MagicMock()
    fake_client.list_collections.return_value = [SimpleNamespace(name="articles")]
    fake_coll = MagicMock()
    fake_coll.count.return_value = 0
    fake_coll.get.return_value = {"ids": [], "metadatas": [], "documents": []}
    fake_client.get_collection.return_value = fake_coll
    mock_chroma_client.return_value = fake_client

    import scripts.dev.verify_chroma_parity as vcp

    # Patch the embedding model to return a simple vector and ensure upsert is called
    with patch("agents.memory.tools.get_embedding_model") as mock_get_model:
        mdl = MagicMock()
        mdl.encode.return_value = [0.1, 0.2, 0.3]
        mock_get_model.return_value = mdl

        rc = vcp.main(["--repair", "--confirm"])  # actually perform repair

    assert rc == 0
    # upsert should have been called for the missing id
    assert fake_coll.upsert.called
    # ensure metrics saw the repair events
    calls = [c[0][0] for c in mock_get_metrics.return_value.record_parity_repair.call_args_list]
    assert "inserted" in calls
    assert "repair_success" in calls
