from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents.common.agent_chain_harness import AgentChainResult, NormalizedArticle
from agents.common.editorial_harness_runner import AgentChainRunner, ArtifactWriter
from agents.common.normalized_article_repository import ArticleCandidate


@dataclass
class _StubMetrics:
    recorded: list[str]
    acceptance: list[float]

    def record_editorial_result(self, result: str) -> None:
        self.recorded.append(result)

    def observe_editorial_acceptance(self, score: float) -> None:
        self.acceptance.append(score)


class _StubHarness:
    def __init__(self, result: AgentChainResult):
        self.result = result
        self.calls = 0

    def run_article(self, article: NormalizedArticle) -> AgentChainResult:
        self.calls += 1
        return self.result


class _StubRepository:
    def __init__(self, candidates):
        self._candidates = candidates

    def fetch_candidates(self, **_):
        return list(self._candidates)


class _StubPersistence:
    def __init__(self):
        self.saved = []

    def save(self, article_row, result):
        self.saved.append((article_row, result))


def test_runner_persists_and_records_metrics(tmp_path):
    article = NormalizedArticle(
        article_id="1",
        url="https://example.com",
        title="Title",
        text="Content" * 100,
        metadata={},
    )
    candidate = ArticleCandidate(row={"id": 1, "url": article.url}, article=article)
    result = AgentChainResult(
        article_id="1",
        story_brief={"summary": "brief"},
        fact_checks=[{"verdict": "verified", "claim": "c"}],
        draft={"summary": "draft"},
        acceptance_score=0.9,
        needs_followup=False,
    )
    repository = _StubRepository([candidate])
    harness = _StubHarness(result)
    persistence = _StubPersistence()
    metrics = _StubMetrics(recorded=[], acceptance=[])
    artifact_writer = ArtifactWriter(tmp_path)

    runner = AgentChainRunner(
        repository=repository,
        harness=harness,
        persistence=persistence,
        metrics=metrics,
        artifact_writer=artifact_writer,
    )

    outputs = runner.run(limit=1)

    assert outputs == [result]
    assert persistence.saved[0][0]["id"] == 1
    assert metrics.recorded == ["accepted"]
    assert metrics.acceptance == [0.9]
    written = next(tmp_path.iterdir())
    assert written.name == "1.json"
    assert harness.calls == 1
