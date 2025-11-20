"""
Analyst Schemas - Output datatypes for Analyst agent

Defines minimal dataclasses used for AnalysisReport and Claim objects.
"""
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ClaimVerdict:
    """Verdict for a single claim from fact-checker."""
    claim_text: str
    verdict: str  # 'verified', 'questionable', 'false', 'unverifiable'
    confidence: float
    evidence: Optional[List[Dict[str, Any]]] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["confidence"] = float(d["confidence"])
        return d


@dataclass
class SourceFactCheck:
    """Per-article fact-check result."""
    article_id: str
    fact_check_status: str  # 'passed', 'failed', 'needs_review', 'pending'
    overall_score: float
    claim_verdicts: Optional[List[ClaimVerdict]] = field(default_factory=list)
    credibility_score: Optional[float] = None
    source_url: Optional[str] = None
    processed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    fact_check_trace: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "fact_check_status": self.fact_check_status,
            "overall_score": float(self.overall_score),
            "claim_verdicts": [cv.to_dict() for cv in (self.claim_verdicts or [])],
            "credibility_score": float(self.credibility_score) if self.credibility_score else None,
            "source_url": self.source_url,
            "processed_at": self.processed_at,
            "fact_check_trace": self.fact_check_trace,
        }


@dataclass
class Claim:
    claim_text: str
    start: Optional[int] = None
    end: Optional[int] = None
    confidence: float = 0.5
    claim_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["confidence"] = float(d["confidence"])
        return d


@dataclass
class PerArticleAnalysis:
    article_id: Optional[str] = None
    language: Optional[str] = "en"
    sentiment: Optional[Dict[str, Any]] = None
    bias: Optional[Dict[str, Any]] = None
    entities: Optional[List[Dict[str, Any]]] = None
    claims: Optional[List[Claim]] = None
    source_fact_check: Optional[SourceFactCheck] = None
    processing_time_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "language": self.language,
            "sentiment": self.sentiment,
            "bias": self.bias,
            "entities": self.entities,
            "claims": [c.to_dict() for c in self.claims or []],
            "source_fact_check": self.source_fact_check.to_dict() if self.source_fact_check else None,
            "processing_time_seconds": self.processing_time_seconds,
        }


@dataclass
class AnalysisReport:
    cluster_id: Optional[str] = None
    language: Optional[str] = "en"
    articles_count: int = 0
    aggregate_sentiment: Optional[Dict[str, Any]] = None
    aggregate_bias: Optional[Dict[str, Any]] = None
    entities: Optional[List[Dict[str, Any]]] = None
    primary_claims: Optional[List[Claim]] = None
    per_article: Optional[List[PerArticleAnalysis]] = None
    source_fact_checks: Optional[List[SourceFactCheck]] = field(default_factory=list)
    cluster_fact_check_summary: Optional[Dict[str, Any]] = None
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "language": self.language,
            "articles_count": self.articles_count,
            "aggregate_sentiment": self.aggregate_sentiment,
            "aggregate_bias": self.aggregate_bias,
            "entities": self.entities or [],
            "primary_claims": [c.to_dict() for c in (self.primary_claims or [])],
            "per_article": [p.to_dict() for p in (self.per_article or [])],
            "source_fact_checks": [sfc.to_dict() for sfc in (self.source_fact_checks or [])],
            "cluster_fact_check_summary": self.cluster_fact_check_summary,
            "generated_at": self.generated_at,
        }
