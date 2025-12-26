"""CI-safe smoke tests for the shared Mistral adapters."""
from __future__ import annotations

from typing import Any

from agents.analyst.mistral_adapter import AnalystMistralAdapter
from agents.chief_editor.mistral_adapter import ChiefEditorMistralAdapter
from agents.journalist.mistral_adapter import JournalistMistralAdapter
from agents.reasoning.mistral_adapter import ReasoningMistralAdapter
from agents.synthesizer.mistral_adapter import SynthesizerMistralAdapter
from agents.tools.mistral_re_ranker_adapter import ReRankerMistralAdapter
from agents.tools.re_ranker_7b import ReRankCandidate


def _stub_chat(adapter: Any, return_value: dict[str, Any]):
    captured: dict[str, Any] = {}

    def fake(messages: list[dict[str, str]]):
        captured["messages"] = messages
        return return_value

    adapter._chat_json = fake  # type: ignore[attr-defined]
    return captured


def test_journalist_adapter_includes_url_and_title():
    adapter = JournalistMistralAdapter()
    captured = _stub_chat(adapter, {"headline": "Mock"})

    doc = adapter.generate_story_brief(markdown="Hello world", url="https://example.com", title="Sample")

    assert doc == {"headline": "Mock", "url": "https://example.com"}
    body = captured["messages"][1]["content"]
    assert "Title: Sample" in body
    assert "URL: https://example.com" in body


def test_journalist_adapter_returns_none_without_content():
    adapter = JournalistMistralAdapter()
    assert adapter.generate_story_brief(markdown=None, html=None) is None


def test_chief_editor_adapter_embeds_assignment():
    adapter = ChiefEditorMistralAdapter()
    captured = _stub_chat(adapter, {"priority": "high"})

    doc = adapter.review_content("Copy", {"assignment": "Budget", "risk": 0.2})

    assert doc == {"priority": "high"}
    body = captured["messages"][1]["content"]
    assert "Assignment: Budget" in body
    assert "risk" in body


def test_chief_editor_adapter_returns_none_for_empty_copy():
    adapter = ChiefEditorMistralAdapter()
    assert adapter.review_content("", {}) is None


def test_reasoning_adapter_defaults_when_no_facts():
    adapter = ReasoningMistralAdapter()
    captured = _stub_chat(adapter, {"verdict": "unclear"})

    doc = adapter.analyze("Is the claim valid?", None)

    assert doc == {"verdict": "unclear"}
    body = captured["messages"][1]["content"]
    assert "None provided" in body


def test_synthesizer_adapter_requires_articles():
    adapter = SynthesizerMistralAdapter()
    assert adapter.summarize_cluster([]) is None


def test_synthesizer_adapter_joins_articles():
    adapter = SynthesizerMistralAdapter()
    captured = _stub_chat(adapter, {"summary": "ok"})

    doc = adapter.summarize_cluster(["first article", "second"], context="Breaking")

    assert doc == {"summary": "ok"}
    body = captured["messages"][1]["content"]
    assert "Context: Breaking" in body
    assert "first article" in body and "second" in body
    assert "\n---\n" in body


def test_analyst_adapter_normalizes_payload():
    adapter = AnalystMistralAdapter()
    captured = _stub_chat(
        adapter,
        {
            "sentiment_label": "positive",
            "sentiment_confidence": 0.88,
            "bias_score": 0.4,
            "bias_level": "medium",
            "bias_confidence": 0.7,
            "rationale": "Sample",
        },
    )

    result = adapter.classify("This is the text")

    assert result is not None
    assert result.sentiment["dominant_sentiment"] == "positive"
    assert result.bias["bias_level"] == "medium"
    assert "Text to evaluate" in captured["messages"][1]["content"]


def test_reranker_adapter_emits_scores_in_order():
    adapter = ReRankerMistralAdapter()
    captured = _stub_chat(
        adapter,
        {"scores": [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.2}]},
    )

    cands = [ReRankCandidate(id="a", text="alpha"), ReRankCandidate(id="b", text="beta")]
    scores = adapter.score_candidates("query", cands)

    assert scores == [0.9, 0.2]
    body = captured["messages"][1]["content"]
    assert "Candidates:" in body
    assert "id=a" in body and "id=b" in body
