from datetime import datetime, timezone
from prometheus_client import CollectorRegistry

from monitoring.core.metrics_collector import EnhancedMetricsCollector
from monitoring.core.custom_metrics import CustomMetrics, ContentMetrics, ContentType, QualityMetric, ProcessingStage, SentimentType


def test_record_content_ingestion_and_stage():
    registry = CollectorRegistry()
    collector = EnhancedMetricsCollector("cm-agent", registry=registry)
    cm = CustomMetrics("cm-agent", collector)

    # Record ingestion with id
    cm.record_content_ingestion(ContentType.ARTICLE, "rss", "sourceA", content_id="cid1")
    assert "cid1" in cm._processing_start_times

    # Simulate a short processing stage
    cm._processing_start_times["cid2"] = 0.1
    # record processing stage for cid2 with explicit duration
    cm.record_processing_stage("cid2", ProcessingStage.ANALYSIS, duration=0.5)


def test_record_complete_content_metrics_and_stats():
    registry = CollectorRegistry()
    collector = EnhancedMetricsCollector("cm-agent2", registry=registry)
    cm = CustomMetrics("cm-agent2", collector)

    now = datetime.now(timezone.utc)
    metrics = ContentMetrics(
        content_id="abc",
        content_type=ContentType.ARTICLE,
        source="src",
        processing_time=1.5,
        quality_scores={QualityMetric.ACCURACY: 0.9},
        word_count=100,
        entities_extracted=2,
        sentiment=SentimentType.POSITIVE,
        bias_score=0.1,
        fact_check_result="ok",
        timestamp=now
    )

    cm.record_complete_content_metrics(metrics)

    stats = cm.get_processing_stats()
    assert stats["total_processed"] >= 1
