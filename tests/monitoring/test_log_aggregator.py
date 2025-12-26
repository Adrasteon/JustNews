import asyncio
from datetime import UTC, datetime

from monitoring.core.log_aggregator import LogAggregator, StorageBackend
from monitoring.core.log_collector import LogEntry, LogLevel


def make_entry():
    return LogEntry(
        timestamp=datetime.now(UTC),
        level=LogLevel.INFO,
        logger_name="logger",
        message="test",
        agent_name="agent",
    )


def test_aggregate_flush_file_backend(tmp_path, monkeypatch):
    # Prevent background tasks from being scheduled
    def _fake_create_task(coro):
        # close coroutine to avoid un-awaited coroutine warnings in tests
        try:
            coro.close()
        except Exception:
            pass
        return None

    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)

    cfg = {
        "aggregation": {
            "strategy": "time_window",
            "time_window_seconds": 0,
            "flush_interval_seconds": 1,
            "max_batch_size": 10,
            "max_buffer_size": 100,
        },
        "storage": {"backend": StorageBackend.FILE, "file_path": str(tmp_path)},
    }

    agg = LogAggregator(cfg)

    # Add some entries
    e1 = make_entry()
    e2 = make_entry()

    # Add items directly to buffer and flush explicitly
    agg._log_buffer.append(e1)
    agg._log_buffer.append(e2)
    asyncio.run(agg._flush_buffer())

    # Check that files were written
    files = list(tmp_path.glob("**/logs_*.json"))
    assert files, "No batch files written to disk"
    assert agg._batches_flushed >= 1


def test_custom_backend_called(monkeypatch):
    monkeypatch.setattr(asyncio, "create_task", lambda coro: None)

    cfg = {
        "aggregation": {
            "strategy": "time_window",
            "time_window_seconds": 0,
            "flush_interval_seconds": 1,
        },
        "storage": {"backend": StorageBackend.FILE, "file_path": "tests/tmp_agg"},
    }
    agg = LogAggregator(cfg)

    called = []

    async def custom_backend(batch):
        called.append(len(batch))

    agg.add_storage_backend(custom_backend)

    e = make_entry()
    asyncio.run(agg.aggregate_log(e))
    asyncio.run(agg._flush_buffer())

    assert called and called[0] >= 1
