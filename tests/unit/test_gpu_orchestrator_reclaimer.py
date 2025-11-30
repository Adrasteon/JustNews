import json
from unittest.mock import MagicMock, patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine


def make_entry(msg_id, job_id, payload, idle):
    # For xpending_range -> (id, consumer, idle, delivered_count)
    return (msg_id, 'consumer', idle, 1)


def make_xrange_entry(msg_id, job_id, payload):
    # redis.xrange returns list of tuples (id, {b'job_id': b'j1', b'payload': b'{}'})
    fields = {b'job_id': job_id.encode('utf-8'), b'payload': json.dumps(payload).encode('utf-8')}
    return (msg_id, fields)


def test_reclaimer_moves_to_dlq_on_max_attempts(monkeypatch):
    # Setup fake redis client
    fake_redis = MagicMock()
    # Pretend xpending_range returns one stale message
    fake_redis.xpending_range.return_value = [make_entry('1-0', 'j1', {'some': 'val'}, 120000)]
    fake_redis.xrange.return_value = [make_xrange_entry('1-0', 'j1', {'some': 'val'})]
    # track xadd to dlq and xack
    fake_redis.xadd = MagicMock()
    fake_redis.xack = MagicMock()

    # Setup fake db service with existing attempts >= max-1 so next attempt triggers DLQ
    cursor = MagicMock()
    # first SELECT attempts returns (4,) (i.e., attempts=4)
    cursor.fetchone.side_effect = [(4,)]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    fake_service = MagicMock()
    fake_service.mb_conn = conn

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=fake_service):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = fake_redis
        engine._job_retry_max = 5

        # run a single reclaim pass
        engine._reclaimer_pass()

        # xadd should have been called to move to DLQ
        assert fake_redis.xadd.called
        assert fake_redis.xack.called
        # DB updated (ensure some UPDATE touched orchestrator_jobs)
        executed_sqls = [c[0][0] for c in conn.cursor.return_value.execute.call_args_list]
        assert any('orchestrator_jobs' in sql for sql in executed_sqls)


def test_reclaimer_requeues_when_attempts_less_than_max(monkeypatch):
    fake_redis = MagicMock()
    fake_redis.xpending_range.return_value = [make_entry('2-0', 'j2', {}, 60000)]
    fake_redis.xrange.return_value = [make_xrange_entry('2-0', 'j2', {'x': 1})]
    fake_redis.xadd = MagicMock()
    fake_redis.xack = MagicMock()

    cursor = MagicMock()
    # SELECT attempts returns (1,)
    cursor.fetchone.side_effect = [(1,)]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    fake_service = MagicMock()
    fake_service.mb_conn = conn

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=fake_service):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = fake_redis
        engine._job_retry_max = 5

        engine._reclaimer_pass()

        # Should requeue (add) and ack original rather than DLQ
        assert fake_redis.xadd.called
        assert fake_redis.xack.called
        # DB updated attempts (ensure an UPDATE touched orchestrator_jobs)
        executed_sqls = [c[0][0] for c in conn.cursor.return_value.execute.call_args_list]
        assert any('orchestrator_jobs' in sql for sql in executed_sqls)
