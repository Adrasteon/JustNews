import importlib
import pytest
from fastapi.testclient import TestClient


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, q, params=None):
        pass

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeDB:
    def __init__(self, rows):
        self.mb_conn = self
        self._rows = rows

    def cursor(self, dictionary=False):
        return FakeCursor(self._rows)

    def close(self):
        pass


def test_list_drafts(monkeypatch):
    from config.core import get_config
    cfg = get_config()
    cfg.system.persistence.synthesized_article_storage = 'synthesized_articles'

    # Fake DB return
    rows = [{
        'id': 1,
        'story_id': 's1',
        'title': 'Test',
        'summary': 'Short',
        'is_published': False,
        'created_at': '2025-11-20T00:00:00'
    }]

    fake = FakeDB(rows)
    monkeypatch.setattr('database.utils.migrated_database_utils.create_database_service', lambda: fake)

    ce = importlib.import_module('agents.chief_editor.main')
    client = TestClient(ce.app)
    resp = client.get('/api/v1/articles/drafts')
    assert resp.status_code == 200
    data = resp.json()
    assert 'drafts' in data
    assert data['drafts'][0]['story_id'] == 's1'
