import json
from unittest.mock import MagicMock, patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine, ALLOCATIONS


def make_cursor_with_status(status_val):
    cursor = MagicMock()
    # For SELECT ... FOR UPDATE we'll return tuple with status
    cursor.fetchone.side_effect = [(status_val,)]
    return cursor


def test_claim_job_and_lease_success(monkeypatch):
    # Ensure ALLOCATIONS reset
    ALLOCATIONS.clear()

    cursor = make_cursor_with_status('pending')
    conn = MagicMock()
    conn.cursor.return_value = cursor

    fake_service = MagicMock()
    fake_service.mb_conn = conn

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=fake_service):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)

        res = engine.claim_job_and_lease('job-123', 'agent-test', min_memory_mb=0)

        assert res.get('claimed') is True
        token = res.get('token')
        assert token in ALLOCATIONS

        # Ensure DB statements included SELECT FOR UPDATE, UPDATE and INSERT
        executed_sqls = [call[0][0] for call in conn.cursor.return_value.execute.call_args_list]
        assert any('SELECT status FROM orchestrator_jobs' in s and 'FOR UPDATE' in s for s in executed_sqls)
        assert any('UPDATE orchestrator_jobs SET status' in s for s in executed_sqls)
        assert any('INSERT INTO orchestrator_leases' in s for s in executed_sqls)
        # commit should be called
        assert conn.commit.called


def test_claim_job_and_lease_already_claimed(monkeypatch):
    cursor = make_cursor_with_status('claimed')
    conn = MagicMock()
    conn.cursor.return_value = cursor

    fake_service = MagicMock()
    fake_service.mb_conn = conn

    with patch('agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service', return_value=fake_service):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        res = engine.claim_job_and_lease('job-xyz', 'agent-test')

        assert res.get('claimed') is False
        assert res.get('reason') == 'not_pending'
        # No commit should be attempted when not pending
        assert not conn.commit.called
