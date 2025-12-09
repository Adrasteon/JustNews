import json

import pytest

from agents.common import ingest


class FakeCursor:
    def __init__(self, update_affects=1, insert_lastrowid=200):
        self.rowcount = 0
        self.update_affects = update_affects
        self.insert_lastrowid = insert_lastrowid
        self.lastrowid = None
        self._fetched = None
        self.closed = False

    def execute(self, sql, params=None):
        # Decide behaviour based on SQL
        if sql.strip().startswith('UPDATE sources SET canonical'):
            # Simulate domain-based update
            self.rowcount = self.update_affects
        elif sql.strip().startswith('SELECT id FROM sources'):
            # Setup fetchone result
            self._fetched = {'id': 123}
            self.rowcount = 1
        elif sql.strip().startswith('INSERT INTO'):
            # Simulate insert
            self.lastrowid = self.insert_lastrowid
            self.rowcount = 1
        else:
            # Other queries (article_source_map insert)
            self.rowcount = 1

    def fetchone(self):
        return self._fetched

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self, dictionary=False, buffered=False):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True

    def rollback(self):
        pass


class FakeService:
    def __init__(self, conn):
        self._conn = conn

    def get_connection(self):
        return self._conn


def test_ingest_article_db_updates_existing_domain(monkeypatch):
    # Simulate update affecting an existing domain row
    fake_cur = FakeCursor(update_affects=1)
    fake_conn = FakeConn(fake_cur)
    fake_svc = FakeService(fake_conn)

    import database.utils.migrated_database_utils as dbmod
    monkeypatch.setattr(dbmod, 'create_database_service', lambda: fake_svc)

    payload = {
        'url': 'https://example.com/article/1',
        'url_hash': 'h1',
        'domain': 'example.com',
        'canonical': 'https://example.com',
        'publisher_meta': {'last_crawled': '2025-01-01T00:00:00Z'},
        'extraction_metadata': {'modal_handler': {'modal_detected': True}},
        'article_id': 42,
    }

    result = ingest.ingest_article_db(payload, dsn='unused')
    # The source_id should be the id returned by the lookup after update
    assert result['source_id'] == 123
    assert result['article_id'] == 42


def test_ingest_article_db_inserts_when_no_domain_present(monkeypatch):
    # Simulate update affecting 0 rows and insert happens
    fake_cur = FakeCursor(update_affects=0, insert_lastrowid=999)
    fake_conn = FakeConn(fake_cur)
    fake_svc = FakeService(fake_conn)

    import database.utils.migrated_database_utils as dbmod
    monkeypatch.setattr(dbmod, 'create_database_service', lambda: fake_svc)

    payload = {
        'url': 'https://example.org/article/2',
        'url_hash': 'h2',
        'domain': 'example.org',
        'canonical': 'https://example.org',
        'publisher_meta': {'last_crawled': '2025-02-02T00:00:00Z'},
        'extraction_metadata': {},
        'article_id': 43,
    }

    result = ingest.ingest_article_db(payload, dsn='unused')
    # When no domain exists, script should insert and return lastrowid
    assert result['source_id'] == 999
    assert result['article_id'] == 43
