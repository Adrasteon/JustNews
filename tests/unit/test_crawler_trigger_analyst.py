import os
import json
import time

import pytest

from agents.crawler.main import trigger_analyst_for_articles


class DummyResponse:
    def __init__(self, status_code=200, ok=True):
        self.status_code = status_code
        self.ok = ok

    def raise_for_status(self):
        if not self.ok or self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def test_trigger_analyst_mcp(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return DummyResponse(200, True)

    monkeypatch.setattr('agents.crawler.main.requests.post', fake_post)
    monkeypatch.setenv('CRAWLER_TRIGGER_ANALYST_AFTER_CRAWL', 'true')
    monkeypatch.setenv('CRAWLER_ANALYST_MODE', 'mcp')

    articles = [{'id': 1, 'analyzed': False}, {'id': 2, 'analyzed': False}, {'id': 3, 'analyzed': True}, {'id': None}]
    n = trigger_analyst_for_articles(articles)

    assert n == 2
    assert len(calls) == 2
    for url, payload in calls:
        assert url.endswith('/call')
        assert payload['agent'] == 'analyst'
        assert payload['tool'] == 'analyze_article'


def test_trigger_analyst_orchestrator(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return DummyResponse(200, True)

    monkeypatch.setattr('agents.crawler.main.requests.post', fake_post)
    monkeypatch.setenv('CRAWLER_TRIGGER_ANALYST_AFTER_CRAWL', 'true')
    monkeypatch.setenv('CRAWLER_ANALYST_MODE', 'orchestrator')

    articles = [{'id': 'a1'}, {'id': 'a2'}]
    n = trigger_analyst_for_articles(articles)

    assert n == 2
    assert all(c[0].endswith('/jobs/submit') for c in calls)


if __name__ == '__main__':
    pytest.main([__file__])
