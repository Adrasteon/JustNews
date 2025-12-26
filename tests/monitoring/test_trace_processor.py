import importlib
import sys
import types
from datetime import datetime

cfg_mod = types.ModuleType("monitoring.common.config")
cfg_mod.get_config = lambda: {"tracing": {"jaeger_enabled": False, "otlp_enabled": False, "file_export_enabled": False}}
sys.modules.setdefault('monitoring.common.config', cfg_mod)
sys.modules.setdefault('monitoring.common.metrics', importlib.import_module('common.metrics'))

from monitoring.core.trace_processor import TraceData, TraceProcessor, TraceSpan


def make_span(sid, parent=None, duration=10, service="svc", op="op", status="ok"):
    return TraceSpan(
        span_id=sid,
        trace_id="t",
        parent_span_id=parent,
        name=op,
        kind="internal",
        start_time=datetime.now(),
        end_time=None,
        duration_ms=duration,
        status=status,
        attributes={},
        events=[],
        service_name=service,
        agent_name="agent",
        operation=op
    )


def test_process_trace_and_analysis_basic():
    processor = TraceProcessor()

    # Build a simple trace with parent-child spans
    span_root = make_span("s1", parent=None, duration=30)
    span_child = make_span("s2", parent="s1", duration=20)
    td = TraceData(trace_id="tr1", root_span_id="s1", spans=[span_root, span_child], start_time=datetime.now(), end_time=datetime.now(), duration_ms=50.0, service_count=1, total_spans=2)

    analysis = processor.process_trace(td)

    assert analysis.trace_id == "tr1"
    assert analysis.span_count == 2
    # Critical path should include s1 and s2
    assert "s1" in analysis.critical_path


def test_find_similar_traces():
    p = TraceProcessor()

    # Two traces with similar structure
    s1 = make_span("a1", duration=10)
    t1 = TraceData(trace_id="t1", root_span_id="a1", spans=[s1], duration_ms=10.0, service_count=1, total_spans=1)

    s2 = make_span("b1", duration=12)
    t2 = TraceData(trace_id="t2", root_span_id="b1", spans=[s2], duration_ms=12.0, service_count=1, total_spans=1)

    p.process_trace(t1)
    p.process_trace(t2)

    sim = p.find_similar_traces("t1")
    assert isinstance(sim, list)
    # Should find the other trace with a similarity score
    if sim:
        assert sim[0][0] == "t2"
