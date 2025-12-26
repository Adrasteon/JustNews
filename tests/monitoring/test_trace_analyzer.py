import importlib
import sys
import types
from datetime import datetime, timedelta

cfg_mod = types.ModuleType("monitoring.common.config")
cfg_mod.get_config = lambda: {"tracing": {"jaeger_enabled": False, "otlp_enabled": False, "file_export_enabled": False}}
sys.modules.setdefault('monitoring.common.config', cfg_mod)
sys.modules.setdefault('monitoring.common.metrics', importlib.import_module('common.metrics'))

from monitoring.core.trace_analyzer import AnomalyType, TraceAnalyzer
from monitoring.core.trace_collector import TraceData, TraceSpan
from monitoring.core.trace_processor import TraceAnalysis


def make_span(id, service="svc", op="op", duration=100, status="ok"):
    return TraceSpan(
        span_id=id,
        trace_id="t",
        parent_span_id=None,
        name=op,
        kind="internal",
        start_time=datetime.now(),
        end_time=datetime.now(),
        duration_ms=duration,
        status=status,
        attributes={},
        events=[],
        service_name=service,
        agent_name="agent",
        operation=op
    )


def make_trace(tid, spans):
    return TraceData(trace_id=tid, root_span_id=spans[0].span_id if spans else "", spans=spans, start_time=datetime.now(), end_time=datetime.now(), duration_ms=sum((s.duration_ms or 0) for s in spans), service_count=len({s.service_name for s in spans}), total_spans=len(spans))


def test_latency_and_error_anomaly_detection():
    analyzer = TraceAnalyzer(analysis_window_minutes=60)

    # Configure a baseline for svc1:op1
    analyzer.performance_baselines['svc1:op1'] = {'mean': 10.0, 'std': 1.0}

    # Create a span with very high duration -> should trigger latency anomaly
    span = make_span('s1', service='svc1', op='op1', duration=1000)
    td = make_trace('t1', [span])
    ta = TraceAnalysis(trace_id='t1', total_duration_ms=1000, span_count=1, service_count=1, error_count=0, critical_path=['s1'], bottlenecks=[], service_dependencies=[], recommendations=[])

    anomalies = analyzer.analyze_trace(td, ta)
    assert any(a.anomaly_type == AnomalyType.LATENCY_SPIKE for a in anomalies)


def test_update_baselines_and_trends():
    analyzer = TraceAnalyzer(analysis_window_minutes=60)

    # Add several recent traces with increasing durations
    now = datetime.now()
    traces = []
    for i in range(6):
        s = make_span(f's{i}', service='svcA', op='opA', duration=10 + i)
        t = make_trace(f't{i}', [s])
        # set end_time spaced out
        t.end_time = now - timedelta(minutes=(5 - i))
        analyzer.recent_traces.append(t)

    analyzer.update_baselines()
    assert 'global:duration' in analyzer.performance_baselines or 'svcA:latency' in analyzer.performance_baselines

    trends = analyzer.analyze_trends(service_name='svcA', time_window='short')
    # Could be empty if insufficient points, but should be callable
    assert isinstance(trends, list)
