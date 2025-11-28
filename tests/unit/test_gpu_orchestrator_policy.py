import os
import time

from fastapi.testclient import TestClient

from agents.gpu_orchestrator.main import app


def test_policy_enforcement_eviction(monkeypatch):
    # run everything in test mode (workers are sleepers)
    monkeypatch.setenv('RE_RANKER_TEST_MODE', '1')

    monkeypatch.setenv('ADMIN_API_KEY', 'adminkey123')
    client = TestClient(app)
    headers = {'Authorization': 'Bearer adminkey123'}

    # ensure policy is permissive initially, set enforcement period short
    resp = client.post('/workers/policy', json={'max_total_workers': 10, 'enforce_period_s': 1}, headers=headers)
    assert resp.status_code == 200

    # create three pools each with 2 workers -> total 6
    for i in range(3):
        r = client.post(
            '/workers/pool',
            json={'pool_id': f'tpool{i}', 'agent': f'tpool{i}', 'num_workers': 2, 'hold_seconds': 30},
            headers=headers,
        )
        assert r.status_code == 200

    # list should show 3 pools
    resp = client.get('/workers/pool', headers=headers)
    pools = resp.json()
    assert len(pools) >= 3

    # now tighten policy to max_total_workers = 3 (should evict at least one pool)
    r = client.post('/workers/policy', json={'max_total_workers': 3, 'enforce_period_s': 1}, headers=headers)
    assert r.status_code == 200

    # wait up to 5s for the enforcer to run
    for _ in range(6):
        resp = client.get('/workers/pool', headers=headers)
        pools = resp.json()
        total_workers = sum(p.get('running_workers', 0) for p in pools)
        if total_workers <= 3:
            break
        time.sleep(1)

    assert total_workers <= 3

    # ensure policy audit entry created
    pf = 'logs/audit/gpu_orchestrator_pool_policy.jsonl'
    assert os.path.exists(pf)
    with open(pf) as f:
        contents = f.read()
    assert 'policy_update' in contents or 'max_total_workers' in contents
