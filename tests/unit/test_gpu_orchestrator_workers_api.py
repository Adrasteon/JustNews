import os
import time
from fastapi.testclient import TestClient

from agents.gpu_orchestrator.main import app


def test_worker_pool_lifecycle(monkeypatch):
    # Ensure test mode so workers behave as lightweight sleepers
    monkeypatch.setenv('RE_RANKER_TEST_MODE', '1')

    client = TestClient(app)

    # create a pool named 'testpool'
    resp = client.post('/workers/pool', params={'agent': 'testpool', 'num_workers': 1, 'hold_seconds': 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get('pool_id') in ('testpool',) or data.get('status') == 'started'

    # list pools and confirm testpool present
    l = client.get('/workers/pool')
    assert l.status_code == 200
    pools = l.json()
    assert any(p['pool_id'] == 'testpool' for p in pools)

    # delete pool
    d = client.delete('/workers/pool/testpool')
    assert d.status_code == 200
    assert d.json().get('status') == 'stopped'
