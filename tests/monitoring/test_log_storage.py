import asyncio
import json
from datetime import UTC, datetime, timedelta

from monitoring.core.log_collector import LogEntry, LogLevel
from monitoring.core.log_storage import (
    LogQuery,
    LogStorage,
    QueryOperator,
)


async def _write_sample_file(storage_path, filename, entries):
    path = storage_path / filename
    await storage_path.mkdir(parents=True, exist_ok=True)
    async with (path).open("w") as f:  # use aiofiles indirectly via LogStorage routines
        f.write(json.dumps([e.to_dict() for e in entries]))


def create_entry(ts, level=LogLevel.INFO, agent_name="test-agent", message="ok"):
    return LogEntry(timestamp=ts, level=level, logger_name="logger", message=message, agent_name=agent_name)


def test_matches_operator_various():
    storage = LogStorage({"storage_path": "tests/tmp_logs", "index_enabled": False, "compression_enabled": False, "cache_ttl_seconds": 1, "index_fields": [], "retention_days": 1})

    # EQUALS
    assert storage._matches_operator("a", "a", QueryOperator.EQUALS)
    assert not storage._matches_operator("a", "b", QueryOperator.EQUALS)

    # CONTAINS
    assert storage._matches_operator("hello world", "world", QueryOperator.CONTAINS)
    # For IN the implementation expects entry_value in query_value
    assert storage._matches_operator(2, [1, 2, 3], QueryOperator.IN)

    # REGEX
    assert storage._matches_operator("error: 123", r"error:\s\d+", QueryOperator.REGEX)


def test_store_and_query_logs(tmp_path):
    cfg = {"storage_path": str(tmp_path), "index_enabled": False, "compression_enabled": False, "cache_ttl_seconds": 1, "index_fields": [], "retention_days": 90}
    storage = LogStorage(cfg)

    now = datetime.now(UTC)
    entries = [
        create_entry(now - timedelta(minutes=1), level=LogLevel.INFO, message="info1"),
        create_entry(now - timedelta(minutes=1), level=LogLevel.ERROR, message="err1"),
    ]

    # store logs
    asyncio.run(storage.store_logs(entries))

    # query without filters -> should return results
    q = LogQuery(filters=None, operators=None, limit=10, offset=0)
    result = asyncio.run(storage.query_logs(q))
    assert result.total_count >= 2

    # query filter by level
    q2 = LogQuery(filters={"level": LogLevel.ERROR}, operators={"level": QueryOperator.EQUALS}, limit=10)
    res2 = asyncio.run(storage.query_logs(q2))
    # Should find at least one error entry
    assert any(e.level == LogLevel.ERROR for e in res2.entries)


def test_cleanup_and_stats(tmp_path):
    # Avoid scheduling background index loading during init (which would require an event loop)
    cfg = {"storage_path": str(tmp_path), "index_enabled": False, "compression_enabled": False, "cache_ttl_seconds": 1, "index_fields": ["level"], "retention_days": 0}
    storage = LogStorage(cfg)

    # Create two files: one old and one new
    old_time = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y%m%d_%H")
    new_time = datetime.now(UTC).strftime("%Y%m%d_%H")

    old_file = tmp_path / f"logs_{old_time}.json"
    new_file = tmp_path / f"logs_{new_time}.json"

    entries_old = [create_entry(datetime.now(UTC) - timedelta(days=2), level=LogLevel.WARNING)]
    entries_new = [create_entry(datetime.now(UTC), level=LogLevel.INFO)]

    # Use the storage's save routine to create files
    asyncio.run(storage._save_log_file(old_file, entries_old))
    asyncio.run(storage._save_log_file(new_file, entries_new))

    # Update index
    asyncio.run(storage._update_index(old_file.name, entries_old))
    asyncio.run(storage._update_index(new_file.name, entries_new))

    # Cleanup with retention 0 should remove the old file
    removed = asyncio.run(storage.cleanup_old_logs(retention_days=1))
    assert removed >= 1

    stats = asyncio.run(storage.get_storage_stats())
    assert "total_files" in stats
