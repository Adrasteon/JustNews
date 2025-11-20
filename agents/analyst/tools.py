"""
Analyst Tools - Utility Functions for Quantitative Analysis

This module provides utility functions for news content quantitative analysis,
including entity extraction, statistical analysis, sentiment/bias detection,
and trend analysis.

Key Functions:
- identify_entities: Extract named entities from text
- analyze_text_statistics: Comprehensive text statistical analysis
- extract_key_metrics: Extract numerical and statistical metrics
- analyze_content_trends: Analyze trends across multiple content pieces
- analyze_sentiment: Sentiment analysis with GPU acceleration
- detect_bias: Bias detection with GPU acceleration
- analyze_sentiment_and_bias: Combined sentiment and bias analysis

All functions include robust error handling, validation, and fallbacks.
"""

import json
import time
from typing import Any

from common.observability import get_logger

from .analyst_engine import AnalystConfig, AnalystEngine

logger = get_logger(__name__)

# Global engine instance
_engine: AnalystEngine | None = None

def get_analyst_engine() -> AnalystEngine:
    """Get or create the global analyst engine instance."""
    global _engine
    if _engine is None:
        config = AnalystConfig()
        _engine = AnalystEngine(config)
    return _engine

async def process_analysis_request(
    text: str,
    analysis_type: str,
    **kwargs
) -> dict[str, Any]:
    """
    Process an analysis request using the analyst engine.

    Args:
        text: Text content to analyze
        analysis_type: Type of analysis to perform
        **kwargs: Additional parameters for analysis

    Returns:
        Analysis results dictionary
    """
    engine = get_analyst_engine()

    try:
        logger.info(f"🔄 Processing {analysis_type} analysis for {len(text)} characters")

        if analysis_type == "entities":
            result = engine.extract_entities(text)
        elif analysis_type == "statistics":
            result = engine.analyze_text_statistics(text)
        elif analysis_type == "metrics":
            url = kwargs.get("url")
            result = engine.extract_key_metrics(text, url)
        elif analysis_type == "sentiment":
            result = engine.analyze_sentiment(text)
        elif analysis_type == "bias":
            result = engine.detect_bias(text)
        elif analysis_type == "sentiment_and_bias":
            result = engine.analyze_sentiment_and_bias(text)
        elif analysis_type == "claims":
            result = engine.extract_claims(text)
        elif analysis_type == "analysis_report":
            # expects `texts` and optional `article_ids` provided as kwargs
            texts = kwargs.get("texts")
            article_ids = kwargs.get("article_ids")
            cluster_id = kwargs.get("cluster_id")
            result = engine.generate_analysis_report(texts or [text], article_ids=article_ids, cluster_id=cluster_id)
        else:
            result = {
                "error": f"Unknown analysis type: {analysis_type}",
                "supported_types": ["sentiment", "entities", "statistics", "metrics", "bias", "sentiment_and_bias"]
            }

        logger.info(f"✅ {analysis_type.capitalize()} analysis completed")
        return result

    except Exception as e:
        logger.error(f"❌ {analysis_type} analysis failed: {e}")
        return {"error": str(e), "details": f"Analysis type: {analysis_type}. Exception: {str(e)}"}

def identify_entities(text: str) -> dict[str, Any]:
    """
    Extract named entities from text.

    This function identifies and categorizes named entities such as persons,
    organizations, locations, dates, and other proper nouns in the text.

    Args:
        text: Input text for entity extraction

    Returns:
        Dictionary containing entity extraction results with:
        - entities: List of entity dictionaries
        - total_entities: Total number of entities found
        - method: Extraction method used
        - text_length: Length of input text
    """
    if not text or not text.strip():
        return {"entities": [], "total_entities": 0, "error": "Empty text provided"}

    engine = get_analyst_engine()
    return engine.extract_entities(text)

def analyze_text_statistics(text: str) -> dict[str, Any]:
    """
    Perform comprehensive statistical analysis of text content.

    This function analyzes various text metrics including word count, sentence
    structure, readability scores, vocabulary diversity, and complexity indicators.

    Args:
        text: Input text for statistical analysis

    Returns:
        Dictionary containing statistical metrics:
        - word_count: Total number of words
        - character_count: Total number of characters
        - sentence_count: Total number of sentences
        - readability_score: Readability score (0-100)
        - avg_word_length: Average word length
        - vocabulary_diversity: Type-token ratio
        - complex_word_ratio: Ratio of complex words
    """
    if not text or not text.strip():
        return {
            "word_count": 0,
            "character_count": 0,
            "sentence_count": 0,
            "error": "Empty text provided"
        }

    engine = get_analyst_engine()
    return engine.analyze_text_statistics(text)

def extract_key_metrics(text: str, url: str = None) -> dict[str, Any]:
    """
    Extract key numerical and statistical metrics from news text.

    This function identifies financial metrics, temporal references,
    statistical data, and geographic information in news content.

    Args:
        text: Article text to analyze
        url: Article URL for context (optional)

    Returns:
        Dictionary containing extracted metrics:
        - metrics: List of metric dictionaries
        - total_metrics: Total number of metrics found
        - text_length: Length of input text
        - url: Article URL (if provided)
    """
    if not text or not text.strip():
        return {"metrics": [], "total_metrics": 0, "error": "Empty text provided"}

    engine = get_analyst_engine()
    return engine.extract_key_metrics(text, url)

def analyze_content_trends(texts: list[str], urls: list[str] = None) -> dict[str, Any]:
    """
    Analyze trends and patterns across multiple content pieces.

    This function identifies common entities, trending topics, and patterns
    across a collection of news articles or content pieces.

    Args:
        texts: List of article texts to analyze
        urls: Corresponding URLs for context (optional)

    Returns:
        Dictionary containing trend analysis:
        - trends: List of trend dictionaries
        - topics: List of topic dictionaries
        - total_texts: Number of texts analyzed
        - total_trends: Total number of trends identified
    """
    if not texts or not any(text.strip() for text in texts):
        return {
            "trends": [],
            "topics": [],
            "error": "No valid texts provided for trend analysis"
        }

    engine = get_analyst_engine()
    return engine.analyze_content_trends(texts, urls)

def analyze_sentiment(text: str) -> dict[str, Any]:
    """
    Analyze sentiment of text content.

    This function determines the overall sentiment (positive, negative, neutral)
    of the provided text using advanced NLP models with GPU acceleration.

    Args:
        text: Text content to analyze for sentiment

    Returns:
        Dictionary containing sentiment analysis results:
        - dominant_sentiment: Primary sentiment (positive/negative/neutral)
        - confidence: Confidence score (0.0-1.0)
        - intensity: Sentiment intensity (mild/moderate/strong)
        - sentiment_scores: Detailed sentiment scores
        - method: Analysis method used
    """
    if not text or not text.strip():
        return {"error": "Empty text provided for sentiment analysis"}

    engine = get_analyst_engine()
    return engine.analyze_sentiment(text)

def detect_bias(text: str) -> dict[str, Any]:
    """
    Detect bias in text content.

    This function analyzes text for potential bias indicators including
    political bias, emotional bias, and factual bias using advanced models.

    Args:
        text: Text content to analyze for bias

    Returns:
        Dictionary containing bias detection results:
        - has_bias: Boolean indicating if bias was detected
        - bias_score: Overall bias score (0.0-1.0)
        - bias_level: Bias level (minimal/low/medium/high)
        - confidence: Detection confidence score
        - political_bias: Political bias component
        - emotional_bias: Emotional bias component
        - factual_bias: Factual bias component
    """
    if not text or not text.strip():
        return {"error": "Empty text provided for bias detection"}

    engine = get_analyst_engine()
    return engine.detect_bias(text)

def analyze_sentiment_and_bias(text: str) -> dict[str, Any]:
    """
    Perform comprehensive analysis combining sentiment and bias detection.

    This function provides a complete analysis including individual sentiment
    and bias assessments plus combined reliability scoring and recommendations.

    Args:
        text: Text content to analyze

    Returns:
        Dictionary containing combined analysis results:
        - sentiment_analysis: Detailed sentiment analysis
        - bias_analysis: Detailed bias detection
        - combined_assessment: Combined reliability and quality scores
        - recommendations: List of analysis recommendations
    """
    if not text or not text.strip():
        return {"error": "Empty text provided for combined analysis"}

    engine = get_analyst_engine()
    return engine.analyze_sentiment_and_bias(text)


def extract_claims(text: str) -> list[dict[str, Any]]:
    """
    Extract claims from the given text using the analyst engine’s heuristics.
    """
    if not text or not text.strip():
        return []

    engine = get_analyst_engine()
    return engine.extract_claims(text)


def generate_analysis_report(texts: list[str], article_ids: list[str] | None = None, cluster_id: str | None = None) -> dict[str, Any]:
    """
    Create a cluster-level AnalysisReport for a list of texts.
    """
    engine = get_analyst_engine()

    # If a cluster_id is provided and no texts are supplied, attempt to fetch the
    # underlying articles from the ClusterFetcher (Chroma / transparency). This
    # centralises the cluster -> articles resolution and keeps the Analyst API
    # backwards-compatible.
    if cluster_id and (not texts or len(texts) == 0):
        try:
            from agents.cluster_fetcher.cluster_fetcher import ClusterFetcher

            fetcher = ClusterFetcher()
            records = fetcher.fetch_cluster(cluster_id=cluster_id)
            if records:
                texts = [r.content for r in records]
                article_ids = [r.article_id for r in records]
        except Exception:
            logger.exception("Failed to fetch cluster content for cluster_id=%s", cluster_id)

    return engine.generate_analysis_report(texts, article_ids=article_ids, cluster_id=cluster_id)

def score_sentiment(text: str) -> dict[str, Any]:
    """
    Legacy sentiment scoring function for backward compatibility.

    Args:
        text: Text to score for sentiment

    Returns:
        Sentiment score results
    """
    return analyze_sentiment(text)

def score_bias(text: str) -> dict[str, Any]:
    """
    Legacy bias scoring function for backward compatibility.

    Args:
        text: Text to score for bias

    Returns:
        Bias score results
    """
    return detect_bias(text)

def log_feedback(event: str, details: dict[str, Any]) -> None:
    """
    Log analysis feedback for monitoring and improvement.

    Args:
        event: Event name or type
        details: Event details and metadata
    """
    try:
        engine = get_analyst_engine()
        # If the engine has a feedback method, use it; otherwise, fall back to logging
        if hasattr(engine, 'log_feedback'):
            try:
                engine.log_feedback(event, details)
            except Exception:
                # Ignore engine-side failures; still log once for observability
                pass
        # Always emit a logger.info call so tests can assert feedback logging
        logger.info(f"Feedback logged: {event}")
    except Exception as e:
        logger.warning(f"Failed to log feedback: {e}")

async def health_check() -> dict[str, Any]:
    """
    Perform health check on analyst components.

    Returns:
        Health check results with component status
    """
    try:
        engine = get_analyst_engine()

        health_status = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "components": {
                "engine": "healthy",
                "spacy_model": "healthy" if engine.spacy_nlp else "unhealthy",
                "ner_pipeline": "healthy" if engine.ner_pipeline else "unhealthy",
                "gpu_analyst": "healthy" if engine.gpu_analyst else "unhealthy"
            },
            "processing_stats": engine.processing_stats
        }

        # Check for any unhealthy components
        unhealthy_components = [k for k, v in health_status["components"].items() if v == "unhealthy"]
        if unhealthy_components:
            health_status["overall_status"] = "degraded"
            health_status["issues"] = [f"Component {comp} is unhealthy" for comp in unhealthy_components]

        logger.info(f"🏥 Analyst health check: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Analyst health check failed: {e}")
        return {
            "timestamp": time.time(),
            "overall_status": "unhealthy",
            "error": str(e)
        }

def validate_analysis_result(result: dict[str, Any], expected_fields: list[str] = None) -> bool:
    """
    Validate analysis result structure.

    Args:
        result: Analysis result to validate
        expected_fields: List of expected fields (optional)

    Returns:
        True if result is valid, False otherwise
    """
    if not isinstance(result, dict):
        return False

    if "error" in result:
        return True  # Error results are valid

    if expected_fields:
        return all(field in result for field in expected_fields)

    # Basic validation for common fields
    return "method" in result or "total_entities" in result or "word_count" in result

def format_analysis_output(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format analysis result for output.

    Args:
        result: Analysis result to format
        format_type: Output format ("json", "text", "markdown")

    Returns:
        Formatted output string
    """
    try:
        if format_type == "json":
            return json.dumps(result, indent=2, default=str)

        elif format_type == "text":
            if "error" in result:
                return f"Error: {result['error']}"

            lines = []
            if "entities" in result:
                lines.append(f"Entities Found: {result.get('total_entities', 0)}")
                for entity in result.get("entities", [])[:5]:  # Show first 5
                    lines.append(f"  - {entity['text']} ({entity['label']})")

            if "word_count" in result:
                lines.append(f"Word Count: {result['word_count']}")
                lines.append(f"Readability Score: {result.get('readability_score', 'N/A')}")

            if "dominant_sentiment" in result:
                lines.append(f"Sentiment: {result['dominant_sentiment']} ({result.get('confidence', 0):.2f})")

            if "bias_level" in result:
                lines.append(f"Bias Level: {result['bias_level']} ({result.get('bias_score', 0):.2f})")

            return "\n".join(lines)

        elif format_type == "markdown":
            if "error" in result:
                return f"## Analysis Error\n\n{result['error']}"

            lines = ["# Analysis Results\n"]

            if "entities" in result:
                lines.append(f"## Entities ({result.get('total_entities', 0)} found)")
                for entity in result.get("entities", [])[:10]:
                    lines.append(f"- **{entity['text']}** - {entity['label']}")

            if "word_count" in result:
                lines.append("## Text Statistics")
                lines.append(f"- Words: {result['word_count']}")
                lines.append(f"- Sentences: {result.get('sentence_count', 'N/A')}")
                lines.append(f"- Readability: {result.get('readability_score', 'N/A')}")

            if "dominant_sentiment" in result:
                lines.append("## Sentiment Analysis")
                lines.append(f"- Sentiment: {result['dominant_sentiment']}")
                lines.append(f"- Confidence: {result.get('confidence', 0):.2f}")
                lines.append(f"- Intensity: {result.get('intensity', 'N/A')}")

            if "bias_level" in result:
                lines.append("## Bias Detection")
                lines.append(f"- Bias Level: {result['bias_level']}")
                lines.append(f"- Bias Score: {result.get('bias_score', 0):.2f}")

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"

# Export main functions
__all__ = [
    'identify_entities',
    'analyze_text_statistics',
    'extract_key_metrics',
    'analyze_content_trends',
    'analyze_sentiment',
    'detect_bias',
    'analyze_sentiment_and_bias',
    'score_sentiment',
    'score_bias',
    'log_feedback',
    'health_check',
    'validate_analysis_result',
    'format_analysis_output',
    'get_analyst_engine'
]
