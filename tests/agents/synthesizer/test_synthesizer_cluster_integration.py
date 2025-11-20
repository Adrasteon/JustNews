import pytest
from unittest.mock import patch, Mock

from agents.synthesizer.synthesizer_engine import SynthesizerEngine, SynthesisResult


class FakeArticle:
    def __init__(self, article_id: str, content: str):
        self.article_id = article_id
        self.content = content

    def to_dict(self):
        return {"article_id": self.article_id, "content": self.content}


@pytest.mark.asyncio
async def test_synthesize_cluster_fact_check_aborts_when_unverified(synthesizer_engine, monkeypatch):
    engine: SynthesizerEngine = synthesizer_engine

    # Patch cluster fetcher to return sample articles
    fake_articles = [FakeArticle("a1", "Test content")]

    class FakeFetcher:
        def fetch_cluster(self, cluster_id=None, article_ids=None, max_results=50, dedupe=True):
            return fake_articles

    monkeypatch.setattr('agents.cluster_fetcher.cluster_fetcher.ClusterFetcher', lambda: FakeFetcher())

    # Patch analyst to return low verified percent
    monkeypatch.setattr('agents.analyst.tools.generate_analysis_report', lambda texts, article_ids=None, cluster_id=None: {"cluster_fact_check_summary": {"percent_verified": 50.0}})

    # Call synthesis with cluster_id and empty articles to trigger fetch
    res = await engine.synthesize_gpu([], max_clusters=2, context="news", options={"cluster_id": "cluster-abc"})

    assert res.get('status') == 'error'
    assert res.get('error') == 'fact_check_failed'
    assert 'analysis_report' in res


@pytest.mark.asyncio
async def test_synthesize_cluster_proceeds_when_verified(synthesizer_engine, monkeypatch):
    engine: SynthesizerEngine = synthesizer_engine

    fake_articles = [FakeArticle("a1", "Test content"), FakeArticle("a2", "Other content")] 

    class FakeFetcher:
        def fetch_cluster(self, cluster_id=None, article_ids=None, max_results=50, dedupe=True):
            return fake_articles

    monkeypatch.setattr('agents.cluster_fetcher.cluster_fetcher.ClusterFetcher', lambda: FakeFetcher())

    # Patch analyst to return high verified percent
    monkeypatch.setattr('agents.analyst.tools.generate_analysis_report', lambda texts, article_ids=None, cluster_id=None: {"cluster_fact_check_summary": {"percent_verified": 80.0}})

    # Patch cluster_articles and aggregate_cluster so we don't require heavy ML dependencies
    async def fake_cluster_articles(texts, max_clusters):
        return {"status":"success", "clusters": [[0, 1]]}

    async def fake_aggregate_cluster(texts):
        return SynthesisResult(success=True, content="Combined synthesis", method="fake", processing_time=0.1, model_used="none", confidence=0.9)

    monkeypatch.setattr(engine, 'cluster_articles', fake_cluster_articles)
    monkeypatch.setattr(engine, 'aggregate_cluster', fake_aggregate_cluster)

    res = await engine.synthesize_gpu([], max_clusters=2, context="news", options={"cluster_id": "cluster-abc"})

    assert res.get('status') == 'success'
    assert 'synthesized_content' in res
    assert res['synthesized_content'] == 'Combined synthesis'
