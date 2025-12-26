import asyncio
import sys
import types as _types
from datetime import datetime, timedelta

# Inject minimal dummy modules required by monitoring.core.trace_collector which is
# imported by trace_storage. Some monitoring internals import monitoring.common.config
# and monitoring.common.metrics which are not available in test isolation; create
# lightweight stand-ins so the module can import successfully.
cfg_mod = _types.ModuleType("monitoring.common.config")
cfg_mod.get_config = lambda: {}
sys.modules["monitoring.common.config"] = cfg_mod

metrics_mod = _types.ModuleType("monitoring.common.metrics")


class _DummyMetric:
    def time(self, *a, **k):
        class Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return Ctx()

    def labels(self, **k):
        class L:
            def inc(self, n: int = 1):
                return None

        return L()


def JustNewsMetrics():
    return _DummyMetric()


metrics_mod.JustNewsMetrics = JustNewsMetrics
sys.modules["monitoring.common.metrics"] = metrics_mod

from monitoring.core.trace_collector import TraceData, TraceSpan
from monitoring.core.trace_storage import FileTraceStorage, TraceQuery


def make_span(span_id: str, trace_id: str, service: str = "svc") -> TraceSpan:
    now = datetime.now()
    return TraceSpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        name="op",
        kind="internal",
        start_time=now,
        end_time=now,
        duration_ms=12.3,
        status="ok",
        attributes={},
        events=[],
        service_name=service,
        agent_name="agent",
        operation="op",
    )


def test_file_trace_storage_store_get_delete_and_stats(tmp_path):
    storage = FileTraceStorage(storage_path=str(tmp_path), retention_days=7)

    trace_id = "t1abcd"
    span = make_span("s1", trace_id)
    td = TraceData(
        trace_id=trace_id,
        root_span_id="s1",
        spans=[span],
        start_time=datetime.now(),
        end_time=datetime.now(),
        duration_ms=12.3,
        service_count=1,
        total_spans=1,
        error_count=0,
        status="active",
    )

    ok = asyncio.run(storage.store_trace(td))
    assert ok is True

    got = asyncio.run(storage.get_trace(trace_id))
    assert got is not None
    assert got.trace_id == trace_id

    stats = asyncio.run(storage.get_stats())
    assert stats.total_traces == 1
    assert stats.total_spans >= 1

    # Delete trace
    deleted = asyncio.run(storage.delete_trace(trace_id))
    assert deleted is True

    # Now it should not be found
    got2 = asyncio.run(storage.get_trace(trace_id))
    assert got2 is None


def test_query_and_cleanup(tmp_path):
    storage = FileTraceStorage(storage_path=str(tmp_path), retention_days=30)

    # Recent trace
    tid_recent = "r1"
    span1 = make_span("sr1", tid_recent, service="svcA")
    td1 = TraceData(
        trace_id=tid_recent,
        root_span_id="sr1",
        spans=[span1],
        start_time=datetime.now(),
        end_time=datetime.now(),
        duration_ms=5.0,
        service_count=1,
        total_spans=1,
        error_count=1,
        status="active",
    )

    # Old trace (10 days ago)
    tid_old = "o1"
    old_start = datetime.now() - timedelta(days=10)
    span2 = TraceSpan(
        span_id="so1",
        trace_id=tid_old,
        parent_span_id=None,
        name="op",
        kind="internal",
        start_time=old_start,
        end_time=old_start,
        duration_ms=3.0,
        status="ok",
        attributes={},
        events=[],
        service_name="svcB",
        agent_name="agent",
        operation="op",
    )
    td2 = TraceData(
        trace_id=tid_old,
        root_span_id="so1",
        spans=[span2],
        start_time=old_start,
        end_time=old_start,
        duration_ms=3.0,
        service_count=1,
        total_spans=1,
        error_count=0,
        status="active",
    )

    assert asyncio.run(storage.store_trace(td1))
    assert asyncio.run(storage.store_trace(td2))

    # Query for errors only
    q = TraceQuery(has_errors=True)
    res = asyncio.run(storage.query_traces(q))
    assert res.total_count >= 1
    assert any(t.trace_id == tid_recent for t in res.traces)

    # Cleanup with retention 1 day should remove the old trace
    deleted_count = asyncio.run(storage.cleanup(retention_days=1))
    assert deleted_count >= 1


import importlib  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402
from datetime import UTC

cfg_mod = types.ModuleType("monitoring.common.config")
cfg_mod.get_config = lambda: {}
sys.modules.setdefault("monitoring.common.config", cfg_mod)
sys.modules.setdefault(
    "monitoring.common.metrics", importlib.import_module("common.metrics")
)

from monitoring.core.trace_collector import TraceSpan


def make_span(sid, duration=20, service="svc", op="op", status="ok"):
    return TraceSpan(
        span_id=sid,
        trace_id="t1",
        parent_span_id=None,
        name=op,
        kind="internal",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        duration_ms=duration,
        status=status,
        attributes={},
        events=[],
        service_name=service,
        agent_name="agent",
        operation=op,
    )


def test_file_trace_storage_store_get_delete_and_stats(tmp_path):
    fs = FileTraceStorage(str(tmp_path))

    s1 = make_span("s1", duration=10)
    s2 = make_span("s2", duration=5)

    td = TraceData(
        trace_id="trace1",
        root_span_id="s1",
        spans=[s1, s2],
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        duration_ms=15.0,
        service_count=1,
        total_spans=2,
        error_count=0,
    )

    ok = asyncio.run(fs.store_trace(td))
    assert ok is True

    got = asyncio.run(fs.get_trace("trace1"))
    assert got is not None and got.trace_id == "trace1"

    # Query traces without filters
    qr = TraceQuery()
    res = asyncio.run(fs.query_traces(qr))
    assert res.total_count >= 1

    # Stats should report at least one trace
    stats = asyncio.run(fs.get_stats())
    assert stats.total_traces >= 1

    # Delete trace
    deleted = asyncio.run(fs.delete_trace("trace1"))
    assert deleted is True


def test_cleanup_old_traces(tmp_path):
    fs = FileTraceStorage(str(tmp_path))

    # Create two traces, one old and one new
    old_span = make_span("old", duration=1)
    # Use naive datetimes to match storage cleanup expectation (which uses naive now())
    old_td = TraceData(
        trace_id="t_old",
        root_span_id="old",
        spans=[old_span],
        start_time=(datetime.now() - timedelta(days=10)),
        end_time=(datetime.now() - timedelta(days=10)),
        duration_ms=1.0,
        service_count=1,
        total_spans=1,
        error_count=0,
    )

    recent_span = make_span("r1", duration=2)
    recent_td = TraceData(
        trace_id="t_new",
        root_span_id="r1",
        spans=[recent_span],
        start_time=datetime.now(),
        end_time=datetime.now(),
        duration_ms=2.0,
        service_count=1,
        total_spans=1,
        error_count=0,
    )

    asyncio.run(fs.store_trace(old_td))
    asyncio.run(fs.store_trace(recent_td))

    # Clean traces older than 5 days should remove the old one
    removed = asyncio.run(fs.cleanup(retention_days=5))
    assert removed >= 1
