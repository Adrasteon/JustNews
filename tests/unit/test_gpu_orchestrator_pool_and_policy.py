import pytest
import time

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine, POLICY


def test_lease_policy_enforced(monkeypatch):
    # Setup: reduce the max per-agent policy
    monkeypatch.setitem(POLICY, 'max_memory_per_agent_mb', 128)

    engine = GPUOrchestratorEngine(bootstrap_external_services=False)

    # Request that exceeds allowed policy should raise HTTPException
    with pytest.raises(Exception) as exc:
        engine.lease_gpu('test_agent', min_memory_mb=256)
    assert 'min_memory_mb' in str(exc.value)


def test_start_worker_pool_emits_instant(monkeypatch, tmp_path):
    engine = GPUOrchestratorEngine(bootstrap_external_services=False)
    # prevent long holds, set test mode env var
    monkeypatch.setenv('RE_RANKER_TEST_MODE', '1')

    events = []
    def fake_emit_instant(**e):
        events.append(e)
        return {}

    monkeypatch.setattr('agents.gpu_orchestrator.gpu_orchestrator_engine.gpu_metrics.emit_instant', fake_emit_instant)

    pool_id = f'testpool-{int(time.time())}'
    res = engine.start_worker_pool(pool_id, model_id='gpt2', adapter=None, num_workers=1, hold_seconds=1)
    assert res.get('status') == 'started'

    # allow process spawn
    time.sleep(0.2)
    pools = engine.list_worker_pools()
    assert any(p['pool_id'] == pool_id for p in pools)

    # ensure we emitted at least one pool worker start event
    assert any(e.get('operation') == 'pool_worker_started' for e in events)

    # cleanup
    engine.stop_worker_pool(pool_id)


def test_policy_setter_and_lease_instant(monkeypatch):
    engine = GPUOrchestratorEngine(bootstrap_external_services=False)
    # set a new policy value
    result = engine.set_policy({'max_memory_per_agent_mb': 256})
    assert result.get('max_memory_per_agent_mb') == 256

    # capture emit instant on lease
    events = []
    def fake_emit_instant(**e):
        events.append(e)
        return {}
    monkeypatch.setattr('agents.gpu_orchestrator.gpu_orchestrator_engine.gpu_metrics.emit_instant', fake_emit_instant)

    # Patch allocator to grant a GPU for the test
    engine._allocate_gpu = lambda req: (True, 0)
    # perform lease
    lease = engine.lease_gpu('test_agent', min_memory_mb=128)
    assert lease.get('granted') is True
    assert any(e.get('operation') == 'lease_granted' for e in events)