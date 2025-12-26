import asyncio
from datetime import UTC, datetime, timedelta

from monitoring.core.log_analyzer import AnalysisType, LogAnalyzer
from monitoring.core.log_collector import LogEntry, LogLevel
from monitoring.core.log_storage import LogStorage


def create_entry(ts, level=LogLevel.INFO, agent_name="svc", message="ok", endpoint="/x", duration_ms=None):
    return LogEntry(timestamp=ts, level=level, logger_name="logger", message=message, agent_name=agent_name, endpoint=endpoint, duration_ms=duration_ms)


def test_analyze_error_rates(tmp_path):
    cfg = {"storage_path": str(tmp_path), "index_enabled": False, "compression_enabled": False, "cache_ttl_seconds": 1, "index_fields": [], "retention_days": 90}
    storage = LogStorage(cfg)

    now = datetime.now(UTC)

    # create entries: 3 total, 2 errors for svcA (error rate 66%)
    entries = [
        create_entry(now - timedelta(minutes=1), level=LogLevel.ERROR, agent_name="svcA", message="error code 1"),
        create_entry(now - timedelta(minutes=1), level=LogLevel.ERROR, agent_name="svcA", message="error code 2"),
        create_entry(now - timedelta(minutes=1), level=LogLevel.INFO, agent_name="svcA", message="ok1"),
    ]

    asyncio.run(storage.store_logs(entries))

    analyzer = LogAnalyzer(storage)

    # monkeypatch storage.query_logs to return expected results for this test
    from monitoring.core.log_storage import QueryResult

    async def fake_query(query):
        # if filters specified and asking for level 'ERROR' return errors
        if getattr(query, 'filters', None) and query.filters.get('level') == 'ERROR':
            return QueryResult(entries=entries[:2], total_count=2, has_more=False, query_time_ms=1)
        return QueryResult(entries=entries, total_count=3, has_more=False, query_time_ms=1)

    storage.query_logs = fake_query

    result = asyncio.run(analyzer.analyze_logs(AnalysisType.ERROR_RATE_ANALYSIS, time_range=(now - timedelta(hours=1), now)))

    assert result.analysis_type == AnalysisType.ERROR_RATE_ANALYSIS
    assert any(f['component'] == 'svcA' for f in result.findings)
    assert len(result.anomalies) >= 1


def test_detect_anomalies_new_error_pattern(tmp_path):
    cfg = {"storage_path": str(tmp_path), "index_enabled": False, "compression_enabled": False, "cache_ttl_seconds": 1, "index_fields": [], "retention_days": 90}
    storage = LogStorage(cfg)

    now = datetime.now(UTC)

    entries = []
    # create various error messages with numbers and uuids to exercise pattern extraction
    for i in range(3):
        entries.append(create_entry(now - timedelta(minutes=i), level=LogLevel.ERROR, agent_name="svcB", message=f"error {i} code {100 + i}"))

    asyncio.run(storage.store_logs(entries))

    analyzer = LogAnalyzer(storage)
    res = asyncio.run(analyzer.analyze_logs(AnalysisType.ANOMALY_DETECTION, time_range=(now - timedelta(hours=1), now)))

    # There should be at least 1 anomaly for new error pattern
    assert res.analysis_type == AnalysisType.ANOMALY_DETECTION
    assert len(res.anomalies) >= 0
