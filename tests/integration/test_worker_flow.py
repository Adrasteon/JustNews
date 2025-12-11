import json
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine
from agents.gpu_orchestrator.worker import Worker


class InMemoryRedisSimple:
    def __init__(self):
        self.streams = {}
        self._pending = {}

    def xadd(self, stream, fields):
        lst = self.streams.setdefault(stream, [])
        mid = f"{len(lst)+1}-0"
        stored = {}
        for k, v in fields.items():
            stored[k if isinstance(k, str) else k] = (v if isinstance(v, bytes) else (json.dumps(v).encode('utf-8')))
        lst.append((mid, stored))
        self._pending.setdefault(stream, []).append((mid, 'consumer', 0, 1))
        return mid

    def xrange(self, stream, a, b):
        return self.streams.get(stream, [])

    def xack(self, stream, group, mid):
        if stream in self._pending:
            self._pending[stream] = [e for e in self._pending[stream] if e[0] != mid]
        return True


def create_sqlite_service():
    import sqlite3
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orchestrator_jobs (
            job_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            owner_pool TEXT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL,
            last_error TEXT NULL
        )
    ''')
    conn.commit()

    # ensure leases table exists for DB-backed paths exercised in integration tests
    c.execute('''
        CREATE TABLE IF NOT EXISTS orchestrator_leases (
            token TEXT PRIMARY KEY,
            agent_name TEXT,
            gpu_index INTEGER NULL,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NULL,
            last_heartbeat TIMESTAMP NULL,
            metadata TEXT NULL
        )
    ''')
    conn.commit()

    class CursorWrapper:
        def __init__(self, conn):
            self._conn = conn
            self._cur = None

        def execute(self, sql, params=None):
            sql2 = sql.replace('%s', '?').replace('NOW()', 'CURRENT_TIMESTAMP')
            if params is None:
                self._cur = self._conn.execute(sql2)
            else:
                self._cur = self._conn.execute(sql2, params)
            return self._cur

        def fetchone(self):
            return self._cur.fetchone() if self._cur is not None else None

        def fetchall(self):
            return self._cur.fetchall() if self._cur is not None else []

        def close(self):
            return None

        @property
        def rowcount(self):
            try:
                return self._cur.rowcount if self._cur is not None else -1
            except Exception:
                return -1

    class MBConn:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self):
            return CursorWrapper(self._conn)

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

    return SimpleNamespace(mb_conn=MBConn(conn))


def test_worker_claims_lease_runs_and_updates_db():
    svc = create_sqlite_service()
    r = InMemoryRedisSimple()

    # add job in DB and stream
    cur = svc.mb_conn._conn = svc.mb_conn._conn
    cur.execute("INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)", ('wjob1','inference_jobs', json.dumps({'foo': 'bar'}), 'pending', 0))
    svc._conn = svc.mb_conn._conn
    svc.mb_conn.commit()

    _mid = r.xadd('stream:orchestrator:inference_jobs', {'job_id': 'wjob1', 'payload': json.dumps({'foo': 'bar'})})

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=svc):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = r

        # make allocate deterministic
        engine._allocate_gpu = lambda req: (True, 0)

        worker = Worker(engine, redis_client=r, agent_name='test_worker')

        processed = worker.run_once()
        assert processed is True

        # verify DB updated to done
        cur = svc.mb_conn._conn.cursor()
        cur.execute('SELECT status FROM orchestrator_jobs WHERE job_id=?', ('wjob1',))
        st = cur.fetchone()
        assert st is not None
        assert st[0] == 'done'


    def test_worker_analysis_job_calls_analyst(monkeypatch):
        svc = create_sqlite_service()
        r = InMemoryRedisSimple()

        # add analysis job in DB and stream
        cur = svc.mb_conn._conn = svc.mb_conn._conn
        cur.execute("INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)", ('analysis-1','analysis', json.dumps({'article_id': 123}), 'pending', 0))
        svc._conn = svc.mb_conn._conn
        svc.mb_conn.commit()

        _mid = r.xadd('stream:orchestrator:inference_jobs', {'job_id': 'analysis-1', 'payload': json.dumps({'article_id': 123}), 'type': 'analysis'})

        with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=svc):
            engine = GPUOrchestratorEngine(bootstrap_external_services=True)
            engine.redis_client = r

            # make allocate deterministic
            engine._allocate_gpu = lambda req: (True, 0)

            called = {}
            def fake_call(agent_name, tool_name, args, kwargs):
                called['agent'] = agent_name
                called['tool'] = tool_name
                called['kwargs'] = kwargs
                return {'status': 'success', 'data': {}}

            monkeypatch.setattr('agents.gpu_orchestrator.worker.mcp_call_agent_tool', fake_call)
            # monkeypatch gpu_metrics start/end to verify instrumentation
            gpu_calls = {}
            def fake_start_event(**meta):
                gpu_calls['start'] = meta
                return 'evt-1'
            def fake_end_event(eid, **outcome):
                gpu_calls['end'] = {'id': eid, **outcome}
                return {}
            monkeypatch.setattr('agents.gpu_orchestrator.worker.gpu_metrics.start_event', fake_start_event)
            monkeypatch.setattr('agents.gpu_orchestrator.worker.gpu_metrics.end_event', fake_end_event)

            worker = Worker(engine, redis_client=r, agent_name='test_worker')

            processed = worker.run_once()
            assert processed is True

            # verify DB updated to done
            cur = svc.mb_conn._conn.cursor()
            cur.execute('SELECT status FROM orchestrator_jobs WHERE job_id=?', ('analysis-1',))
            st = cur.fetchone()
            assert st is not None
            assert st[0] == 'done'
            # and analyze call executed
            assert called.get('agent') == 'analyst'
            assert called.get('tool') == 'analyze_article'
            # ensure GPU instrumentation was invoked
            assert gpu_calls.get('start') is not None
            assert gpu_calls.get('end') is not None


def test_worker_sampling_thread_emits_instants(monkeypatch):
    svc = create_sqlite_service()
    r = InMemoryRedisSimple()

    # add job in DB and stream
    cur = svc.mb_conn._conn = svc.mb_conn._conn
    cur.execute("INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)", ('sampling-job','inference_jobs', json.dumps({'foo': 'bar'}), 'pending', 0))
    svc.mb_conn.commit()
    r.xadd('stream:orchestrator:inference_jobs', {'job_id': 'sampling-job', 'payload': json.dumps({'foo': 'bar'})})

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=svc):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = r
        engine._allocate_gpu = lambda req: (True, 0)

        emitted = {'calls': 0}
        def fake_emit_instant(**event):
            emitted['calls'] += 1
            return {}

        monkeypatch.setattr('agents.gpu_orchestrator.worker.gpu_metrics.emit_instant', fake_emit_instant)

        # handler will sleep for a short duration so sampler runs
        def slow_handler(_payload):
            import time
            time.sleep(0.8)

        worker = Worker(engine, redis_client=r, agent_name='test_worker')
        processed = worker.run_once(handler=slow_handler)
        assert processed is True
        # sampler should have emitted at least a couple of times
        assert emitted['calls'] >= 2


def test_call_analyst_pre_post_emit(monkeypatch):
    svc = create_sqlite_service()
    r = InMemoryRedisSimple()

    # add analysis job in DB and stream
    cur = svc.mb_conn._conn = svc.mb_conn._conn
    cur.execute("INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)", ('analysis-2','analysis', json.dumps({'article_id': 222}), 'pending', 0))
    svc.mb_conn.commit()
    r.xadd('stream:orchestrator:inference_jobs', {'job_id': 'analysis-2', 'payload': {'article_id': 222}, 'type': 'analysis'})

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=svc):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = r
        engine._allocate_gpu = lambda req: (True, 0)

        called = {}
        def fake_call(agent_name, tool_name, args, kwargs):
            called['agent'] = agent_name
            called['tool'] = tool_name
            called['kwargs'] = kwargs
            import time
            time.sleep(0.2)
            return {'status': 'success', 'data': {}}

        monkeypatch.setattr('agents.gpu_orchestrator.worker.mcp_call_agent_tool', fake_call)
        emitted_ops = []
        def fake_emit_instant(**event):
            emitted_ops.append(event.get('operation'))
            return {}
        monkeypatch.setattr('agents.gpu_orchestrator.worker.gpu_metrics.emit_instant', fake_emit_instant)

        worker = Worker(engine, redis_client=r, agent_name='test_worker')
        processed = worker.run_once()
        assert processed is True
        # verify the mcp call executed
        assert called.get('agent') == 'analyst'
        # We expect the sampler and pre/post call instants - the pre/post may fire very quickly
        assert 'job_memory_sample' in emitted_ops
        assert ('call_analyst:pre' in emitted_ops) or ('call_analyst:post' in emitted_ops)


def test_worker_handler_failure_marks_failed_and_sets_last_error():
    svc = create_sqlite_service()
    r = InMemoryRedisSimple()

    # add job in DB and stream
    cur = svc.mb_conn._conn = svc.mb_conn._conn
    cur.execute("INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)", ('wj-fail','inference_jobs', json.dumps({'foo': 'bar'}), 'pending', 0))
    svc._conn = svc.mb_conn._conn
    svc.mb_conn.commit()

    _mid = r.xadd('stream:orchestrator:inference_jobs', {'job_id': 'wj-fail', 'payload': json.dumps({'foo': 'bar'})})

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=svc):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = r

        # ensure lease is granted so we exercise release path
        engine._allocate_gpu = lambda req: (True, 0)

        releases = []
        def fake_release(token):
            releases.append(token)
            return {'released': True}

        engine.release_gpu_lease = fake_release

        # handler raises
        def bad_handler(_):
            raise RuntimeError('boom-handler')

        worker = Worker(engine, redis_client=r, agent_name='test_worker')

        processed = worker.run_once(handler=bad_handler)
        assert processed is True

        # verify DB updated to failed and error set
        cur = svc.mb_conn._conn.cursor()
        cur.execute('SELECT status, last_error FROM orchestrator_jobs WHERE job_id=?', ('wj-fail',))
        st = cur.fetchone()
        assert st is not None
        assert st[0] == 'failed'
        assert 'boom-handler' in (st[1] or '')

        # update path should have released the lease since _allocate returned success
        assert len(releases) == 1


def test_worker_without_lease_still_marks_done_and_failure_works():
    svc = create_sqlite_service()
    r = InMemoryRedisSimple()

    # happy path job (no lease available)
    cur = svc.mb_conn._conn = svc.mb_conn._conn
    cur.execute("INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)", ('wj-nolease','inference_jobs', json.dumps({'a': 1}), 'pending', 0))
    svc.mb_conn.commit()
    r.xadd('stream:orchestrator:inference_jobs', {'job_id': 'wj-nolease', 'payload': json.dumps({'a':1})})

    # failing job without lease
    cur.execute("INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)", ('wj-nolease-fail','inference_jobs', json.dumps({'a': 2}), 'pending', 0))
    svc.mb_conn.commit()
    r.xadd('stream:orchestrator:inference_jobs', {'job_id': 'wj-nolease-fail', 'payload': json.dumps({'a':2})})

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=svc):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = r

        # force allocation to fail (no lease granted)
        engine._allocate_gpu = lambda req: (False, None)

        # run worker for the first message (wj-nolease) and it should succeed
        worker = Worker(engine, redis_client=r, agent_name='test_worker')
        processed = worker.run_once()
        assert processed is True

        cur = svc.mb_conn._conn.cursor()
        cur.execute('SELECT status FROM orchestrator_jobs WHERE job_id=?', ('wj-nolease',))
        st = cur.fetchone()
        assert st is not None
        assert st[0] == 'done'

        # remove the first stream entry so the next run_once will pick the second message
        try:
            r.streams['stream:orchestrator:inference_jobs'].pop(0)
        except Exception:
            pass

        # now process failing handler for second job
        def bad_handler(_):
            raise ValueError('nolease-fail')

        processed = worker.run_once(handler=bad_handler)
        assert processed is True

        cur.execute('SELECT status, last_error FROM orchestrator_jobs WHERE job_id=?', ('wj-nolease-fail',))
        st2 = cur.fetchone()
        assert st2 is not None
        assert st2[0] == 'failed'
        assert 'nolease-fail' in (st2[1] or '')
