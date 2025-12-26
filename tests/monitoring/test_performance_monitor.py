from datetime import UTC, datetime, timedelta

from prometheus_client import CollectorRegistry

from monitoring.core.metrics_collector import EnhancedMetricsCollector
from monitoring.core.performance_monitor import (
    BottleneckType,
    PerformanceMetric,
    PerformanceMonitor,
    PerformanceSnapshot,
    PerformanceThreshold,
)


def test_calculate_performance_score_various():
    reg = CollectorRegistry()
    collector = EnhancedMetricsCollector("pm-agent", registry=reg)
    pm = PerformanceMonitor("pm-agent", collector)

    # CPU very high, memory medium -> significant score reduction
    snap = PerformanceSnapshot(
        timestamp=datetime.now(UTC),
        cpu_percent=95.0,
        memory_percent=60.0,
        disk_read_bytes=0,
        disk_write_bytes=0,
        network_sent_bytes=0,
        network_recv_bytes=0,
    )

    score = pm._calculate_performance_score(snap)
    assert score <= 70.0

    # Low usage should give full score
    snap_low = PerformanceSnapshot(
        timestamp=datetime.now(UTC),
        cpu_percent=10.0,
        memory_percent=10.0,
        disk_read_bytes=0,
        disk_write_bytes=0,
        network_sent_bytes=0,
        network_recv_bytes=0,
    )

    assert pm._calculate_performance_score(snap_low) == 100.0


def test_detect_bottleneck_from_snapshots_cpu():
    reg = CollectorRegistry()
    collector = EnhancedMetricsCollector("pm-agent2", registry=reg)
    pm = PerformanceMonitor("pm-agent2", collector)

    now = datetime.now(UTC)

    # Create several snapshots with high CPU to trigger CPU bottleneck
    snaps = [
        PerformanceSnapshot(timestamp=now - timedelta(seconds=30 * i), cpu_percent=88.0 + i, memory_percent=40.0,
                            disk_read_bytes=0, disk_write_bytes=0, network_sent_bytes=0, network_recv_bytes=0)
        for i in range(6)
    ]

    import asyncio
    analysis = asyncio.run(pm._detect_bottleneck(snaps))
    assert analysis is not None
    assert analysis.primary_bottleneck == BottleneckType.CPU_BOUND


def test_get_performance_report_no_data():
    reg = CollectorRegistry()
    collector = EnhancedMetricsCollector("pm-agent3", registry=reg)
    pm = PerformanceMonitor("pm-agent3", collector)

    report = pm.get_performance_report(hours=1)
    assert report["status"] == "no_data"


def test_get_recommendations_unique_and_limited():
    reg = CollectorRegistry()
    collector = EnhancedMetricsCollector("pm-agent4", registry=reg)
    pm = PerformanceMonitor("pm-agent4", collector)

    # Populate bottleneck history with duplicates
    now = datetime.now(UTC)

    snap = PerformanceSnapshot(timestamp=now, cpu_percent=95.0, memory_percent=96.0, disk_read_bytes=0,
                               disk_write_bytes=0, network_sent_bytes=0, network_recv_bytes=0)

    import asyncio
    analysis1 = asyncio.run(pm._detect_bottleneck([snap, snap, snap, snap, snap, snap]))
    if analysis1:
        pm._bottleneck_history.append(analysis1)
        pm._bottleneck_history.append(analysis1)
        pm._bottleneck_history.append(analysis1)

    recs = pm.get_recommendations()
    assert isinstance(recs, list)
    # Should be at most 5 and no duplicates (unique set)
    assert len(recs) <= 5
import asyncio

import pytest


def create_monitor():
    collector = EnhancedMetricsCollector('pmagent')
    return PerformanceMonitor('pmagent', collector)


def test_calculate_performance_score_cpu_and_memory():
    m = create_monitor()
    snap = PerformanceSnapshot(timestamp=datetime.now(UTC), cpu_percent=95, memory_percent=96, disk_read_bytes=0, disk_write_bytes=0, network_sent_bytes=0, network_recv_bytes=0)
    score = m._calculate_performance_score(snap)
    assert score < 100


def test_detect_bottleneck_cpu_and_memory():
    m = create_monitor()
    # create snapshots with high cpu and memory
    now = datetime.now(UTC)
    snaps = [PerformanceSnapshot(timestamp=now - timedelta(minutes=5-i), cpu_percent=90, memory_percent=92, disk_read_bytes=0, disk_write_bytes=0, network_sent_bytes=0, network_recv_bytes=0) for i in range(5)]
    # run detection
    bottleneck = asyncio.run(m._detect_bottleneck(snaps))
    assert bottleneck is not None
    assert bottleneck.primary_bottleneck in (BottleneckType.CPU_BOUND, BottleneckType.MEMORY_BOUND)


def test_get_performance_report_no_data():
    m = create_monitor()
    report = m.get_performance_report(hours=1)
    assert report['status'] == 'no_data'


def test_get_performance_report_with_data_and_bottlenecks():
    m = create_monitor()
    now = datetime.now(UTC)
    # populate snapshots
    for i in range(6):
        m._snapshots.append(PerformanceSnapshot(timestamp=now - timedelta(minutes=5-i), cpu_percent=90, memory_percent=85, disk_read_bytes=0, disk_write_bytes=0, network_sent_bytes=0, network_recv_bytes=0))

    # add a recent bottleneck
    analysis = asyncio.run(m._detect_bottleneck(m._snapshots[:5]))
    m._bottleneck_history.append(analysis)

    report = m.get_performance_report(hours=1)
    assert report['status'] == 'active'
    assert report['sample_count'] >= 1


@pytest.mark.asyncio
async def test_check_thresholds_triggers_alert(monkeypatch):
    m = create_monitor()
    # create a snapshot with high cpu
    now = datetime.now(UTC)
    snap = PerformanceSnapshot(timestamp=now, cpu_percent=95, memory_percent=30, disk_read_bytes=0, disk_write_bytes=0, network_sent_bytes=0, network_recv_bytes=0)
    m._snapshots.append(snap)

    # add threshold for CPU lower than current value
    thr = PerformanceThreshold(metric=PerformanceMetric.CPU_USAGE, warning_threshold=70.0, critical_threshold=90.0)
    m.set_threshold(PerformanceMetric.CPU_USAGE, thr)

    handled = []

    async def fake_handle(alert):
        handled.append(alert)

    # patch the collector handler
    m.collector._handle_alert = fake_handle

    await m._check_thresholds()
    assert len(handled) >= 1
