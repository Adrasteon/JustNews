import asyncio
from datetime import UTC, datetime, timedelta

from prometheus_client import CollectorRegistry

from monitoring.core.metrics_collector import (
    Alert,
    AlertRule,
    AlertSeverity,
    EnhancedMetricsCollector,
    MetricThreshold,
)


def test_record_business_metric_and_prometheus_counter():
    reg = CollectorRegistry()
    c = EnhancedMetricsCollector("test-agent", registry=reg)

    # Before recording, history is empty
    assert "content_processed" not in c._metric_history

    c.record_business_metric(
        "content_processed", 1.0, labels={"content_type": "article", "stage": "parsed"}
    )

    # History should have one entry
    assert "content_processed" in c._metric_history
    assert len(c._metric_history["content_processed"]) == 1

    # Prometheus counter should have an entry for the given labels
    val = c.registry.get_sample_value(
        "justnews_content_processed_total",
        labels={
            "agent": "test-agent",
            "content_type": "article",
            "processing_stage": "parsed",
        },
    )

    assert val is not None and val > 0


def test_record_performance_metric_updates_baseline():
    reg = CollectorRegistry()
    c = EnhancedMetricsCollector("perf-agent", registry=reg)

    assert "op_x" not in c._performance_baselines
    c.record_performance_metric("op_x", 2.0)
    assert "op_x" in c._performance_baselines

    # Subsequent update should apply exponential moving average
    prev = c._performance_baselines["op_x"]
    c.record_performance_metric("op_x", 1.0)
    assert c._performance_baselines["op_x"] != prev


def test_alert_rules_and_handlers_and_resolution():
    reg = CollectorRegistry()
    c = EnhancedMetricsCollector("alert-agent", registry=reg)

    thresholds = MetricThreshold(warning_threshold=10.0, critical_threshold=20.0)
    rule = AlertRule(
        name="r1",
        metric_name="m1",
        thresholds=thresholds,
        description="desc",
        severity=AlertSeverity.WARNING,
    )

    c.add_alert_rule(rule)
    assert "r1" in c._alert_rules

    c.remove_alert_rule("r1")
    assert "r1" not in c._alert_rules

    received = []

    async def handler(alert: Alert):
        # Append a copy-friendly tuple to avoid test loop issues
        received.append((alert.rule_name, alert.severity, alert.value))

    c.add_alert_handler(handler)

    # Trigger a manual alert using the private API (emulates internal behavior)
    async def trigger_and_wait():
        alert = Alert(
            rule_name="manual",
            severity=AlertSeverity.ERROR,
            message="fail",
            value=1.0,
            threshold=0.5,
            timestamp=datetime.now(UTC),
        )

        await c._handle_alert(alert)

    asyncio.run(trigger_and_wait())

    assert len(received) == 1

    # Test resolve_alert and get_active_alerts flow
    # Add a synthetic active alert and verify resolution
    c._active_alerts["key1"] = Alert(
        rule_name="a1",
        severity=AlertSeverity.WARNING,
        message="",
        value=0.0,
        threshold=1.0,
        timestamp=datetime.now(UTC),
    )

    assert len(c.get_active_alerts()) == 1
    c.resolve_alert("key1")
    assert c._active_alerts["key1"].resolved is True


def test_cleanup_old_data_prunes_history_and_resolved_alerts():
    reg = CollectorRegistry()
    c = EnhancedMetricsCollector("cleanup-agent", registry=reg)

    old_ts = datetime.now(UTC) - timedelta(days=2)
    new_ts = datetime.now(UTC)

    c._metric_history["m1"] = [(old_ts, 1.0), (new_ts, 2.0)]

    # Add a resolved old alert and a recent resolved alert
    old_alert = Alert(
        rule_name="old",
        severity=AlertSeverity.WARNING,
        message="",
        value=0.0,
        threshold=0.0,
        timestamp=old_ts,
        resolved=True,
        resolved_at=old_ts,
    )

    new_alert = Alert(
        rule_name="new",
        severity=AlertSeverity.WARNING,
        message="",
        value=0.0,
        threshold=0.0,
        timestamp=new_ts,
        resolved=True,
        resolved_at=new_ts,
    )

    c._active_alerts["old_key"] = old_alert
    c._active_alerts["new_key"] = new_alert

    asyncio.run(c._cleanup_old_data())

    # Old metric entry pruned
    assert len(c._metric_history["m1"]) == 1

    # Old alert should be removed, new alert remains
    assert "old_key" not in c._active_alerts
    assert "new_key" in c._active_alerts


import pytest  # noqa: E402

from monitoring.core.metrics_collector import (  # noqa: E402
    _enhanced_metrics_instances,
    get_enhanced_metrics_collector,
)


def test_record_business_metric_history_and_prometheus_counter():
    c = EnhancedMetricsCollector("testagent")
    # record business metric and ensure it is stored in history
    c.record_business_metric(
        "content_processed", 1.0, labels={"content_type": "news", "stage": "ingest"}
    )
    assert "content_processed" in c._metric_history
    assert len(c._metric_history["content_processed"]) == 1


def test_record_performance_metric_updates_baselines():
    c = EnhancedMetricsCollector("perfagent")
    c.record_performance_metric("op", 0.1)
    assert "op" in c._performance_baselines
    prev = c._performance_baselines["op"]
    c.record_performance_metric("op", 0.2)
    assert c._performance_baselines["op"] != prev


@pytest.mark.asyncio
async def test_alert_rule_evaluation_triggers_handler(monkeypatch):
    c = EnhancedMetricsCollector("alertagent")

    # create rule: warning if > 1.0
    threshold = MetricThreshold(
        warning_threshold=1.0, critical_threshold=2.0, direction="above"
    )
    rule = AlertRule(
        name="test_rule",
        metric_name="m",
        thresholds=threshold,
        description="d",
        severity=AlertSeverity.WARNING,
    )
    c.add_alert_rule(rule)

    # patch _get_metric_value to return 1.5
    monkeypatch.setattr(
        c, "_get_metric_value", lambda name: asyncio.sleep(0, result=1.5)
    )

    handled = []

    async def handler(alert):
        handled.append(alert)

    c.add_alert_handler(handler)

    await c._evaluate_alert_rules()
    # one active alert should be present and handler called
    assert len(c.get_active_alerts()) >= 1
    assert len(handled) >= 1


def test_cleanup_old_data_removes_old_entries():
    c = EnhancedMetricsCollector("cleanupagent")
    old_ts = datetime.now(UTC) - timedelta(hours=48)
    new_ts = datetime.now(UTC)
    c._metric_history["m"] = [(old_ts, 1.0), (new_ts, 2.0)]
    # add resolved alert older than cutoff
    alert_key = "r1"
    from monitoring.core.metrics_collector import Alert

    alert = Alert(
        rule_name="r1",
        severity=AlertSeverity.WARNING,
        message="x",
        value=1.0,
        threshold=0.5,
        timestamp=new_ts,
        resolved=True,
        resolved_at=old_ts,
    )
    c._active_alerts[alert_key] = alert

    import asyncio

    asyncio.run(c._cleanup_old_data())

    # metric_history should have removed old item
    assert len(c._metric_history["m"]) == 1


def test_get_metrics_summary_and_global_collection():
    name = "summaryagent"
    # ensure singleton behavior
    if name in _enhanced_metrics_instances:
        del _enhanced_metrics_instances[name]

    collector = get_enhanced_metrics_collector(name)
    s = collector.get_metrics_summary()
    assert s["agent"] == name
    assert "timestamp" in s
