from datetime import datetime, timedelta

import importlib, sys, types
# Provide a minimal monitoring.common.config module so imports succeed in tests
cfg_mod = types.ModuleType("monitoring.common.config")
cfg_mod.get_config = lambda: {"tracing": {"jaeger_enabled": False, "otlp_enabled": False, "file_export_enabled": False}}
sys.modules.setdefault('monitoring.common.config', cfg_mod)
# Also make monitoring.common.metrics available by mapping to top-level common.metrics
sys.modules.setdefault('monitoring.common.metrics', importlib.import_module('common.metrics'))

from monitoring.core.trace_collector import TraceSpan, TraceData, TraceCollector


def test_trace_span_and_data_to_dict():
    start = datetime.now()
    span = TraceSpan(
        span_id="s1",
        trace_id="t1",
        parent_span_id=None,
        name="op",
        kind="internal",
        start_time=start,
        end_time=start + timedelta(milliseconds=50),
        duration_ms=50.0,
        status="ok",
        attributes={"a": 1},
        events=[{"e": 1}],
        service_name="svc",
        agent_name="agent",
        operation="op"
    )

    d = TraceData(trace_id="t1", root_span_id="s1", spans=[span], start_time=start, end_time=start + timedelta(milliseconds=50), duration_ms=50.0, service_count=1, total_spans=1)

    sd = span.to_dict()
    td = d.to_dict()

    assert sd["span_id"] == "s1"
    assert td["trace_id"] == "t1"
    assert isinstance(td["spans"], list) and td["spans"][0]["span_id"] == "s1"


def test_collector_stats_and_cleanup(monkeypatch, tmp_path):
    # Prevent exporters and heavy OTEL setup by returning minimal config
    monkeypatch.setattr("monitoring.core.trace_collector.get_config", lambda: {"tracing": {"jaeger_enabled": False, "otlp_enabled": False, "file_export_enabled": False}})

    # Provide a dummy JustNewsMetrics implementation to avoid needing the real metrics
    class DummyMetric:
        def __init__(self, *a, **k):
            pass

        def time(self, *_args, **_kwargs):
            class Ctx:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    return False

            return Ctx()

        def labels(self, *a, **k):
            class LabelObj:
                def inc(self, *_a, **_k):
                    return None

                def set(self, *_a, **_k):
                    return None

                def observe(self, *_a, **_k):
                    return None

            return LabelObj()

    class DummyMetricsFactory:
        def __init__(self, *a, **k):
            pass

        def create_histogram(self, *a, **k):
            return DummyMetric()

        def create_counter(self, *a, **k):
            return DummyMetric()

    monkeypatch.setattr("monitoring.core.trace_collector.JustNewsMetrics", DummyMetricsFactory)
    # Avoid configuring real OpenTelemetry tracer in tests
    monkeypatch.setattr("monitoring.core.trace_collector.TraceCollector._setup_tracing", lambda self: None)

    collector = TraceCollector(service_name="svc", agent_name="agent")

    # Initially no traces
    stats = collector.get_stats()
    assert stats["active_traces"] == 0

    # Add a completed trace older than retention
    old = TraceData(trace_id="old", root_span_id="s", spans=[], start_time=datetime.now() - timedelta(days=2), end_time=datetime.now() - timedelta(days=2), duration_ms=10.0)
    collector.completed_traces["old"] = old

    # Ensure cleanup removes it
    collector.trace_retention_hours = 1
    import asyncio
    asyncio.run(collector.cleanup_old_traces())
    assert "old" not in collector.completed_traces


def test_get_trace_active_and_completed(monkeypatch):
    monkeypatch.setattr("monitoring.core.trace_collector.get_config", lambda: {"tracing": {"jaeger_enabled": False, "otlp_enabled": False, "file_export_enabled": False}})
    class DummyMetric:
        def __init__(self, *a, **k):
            pass

        def time(self, *_args, **_kwargs):
            class Ctx:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    return False

            return Ctx()

        def labels(self, *a, **k):
            class LabelObj:
                def inc(self, *_a, **_k):
                    return None

                def set(self, *_a, **_k):
                    return None

                def observe(self, *_a, **_k):
                    return None

            return LabelObj()

    class DummyMetricsFactory:
        def __init__(self, *a, **k):
            pass

        def create_histogram(self, *a, **k):
            return DummyMetric()

        def create_counter(self, *a, **k):
            return DummyMetric()

    monkeypatch.setattr("monitoring.core.trace_collector.JustNewsMetrics", DummyMetricsFactory)
    monkeypatch.setattr("monitoring.core.trace_collector.TraceCollector._setup_tracing", lambda self: None)

    collector = TraceCollector("svc2", "agent2")

    td_active = TraceData(trace_id="ta", root_span_id="sa")
    td_done = TraceData(trace_id="td", root_span_id="sd")

    collector.active_traces["ta"] = td_active
    collector.completed_traces["td"] = td_done

    assert collector.get_trace("ta") is td_active
    assert collector.get_trace("td") is td_done
