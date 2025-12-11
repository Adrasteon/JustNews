import json
import pytest

from agents.analyst.main import analyze_article_endpoint, ToolCall


def test_analyze_article_instrumentation(monkeypatch):
    # patch fetch_article_from_db to return a dummy article
    def fake_fetch(article_id):
        return {'id': article_id, 'content': 'hello world', 'analyzed': False}

    monkeypatch.setattr('agents.analyst.main.fetch_article_from_db', fake_fetch)

    # patch update_article_status to no-op
    monkeypatch.setattr('agents.analyst.main.update_article_status', lambda *args, **kwargs: None)

    # patch gpu metrics
    called = {}
    def fake_start_event(**meta):
        called['start'] = meta
        return 'evt-123'

    def fake_end_event(eid, **kwargs):
        called['end'] = {'id': eid, **kwargs}
        return {}

    monkeypatch.setattr('agents.analyst.main.gpu_metrics.start_event', fake_start_event)
    monkeypatch.setattr('agents.analyst.main.gpu_metrics.end_event', fake_end_event)

    call = ToolCall(args=[], kwargs={'article_id': 42})
    res = analyze_article_endpoint(call)
    assert res['status'] == 'success'
    assert called.get('start') is not None
    assert called.get('end') is not None
