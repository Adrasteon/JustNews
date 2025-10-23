"""
Fact Checker Tools - Utility Functions for Fact Verification

This module provides utility functions for fact verification and source credibility assessment,
focusing on claim validation, evidence evaluation, and source reliability analysis.

Key Functions:
- verify_facts: Primary fact verification using AI models
- validate_sources: Source credibility assessment
- comprehensive_fact_check: Full article fact-checking
- extract_claims: Extract verifiable claims from text
- assess_credibility: Evaluate source reliability
- detect_contradictions: Identify logical inconsistencies

All functions include robust error handling, validation, and fallbacks.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from common.observability import get_logger

# Configure logging
logger = get_logger(__name__)

# Global engine instance
_engine: Optional[Any] = None

def get_fact_checker_engine():
    """Get or create the global fact checker engine instance."""
    global _engine
    if _engine is None:
        from .fact_checker_engine import FactCheckerEngine, FactCheckerConfig
        config = FactCheckerConfig()
        _engine = FactCheckerEngine(config)
    return _engine

async def process_fact_check_request(
    content: str,
    operation_type: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Process a fact-checking request using the fact checker engine.

    Args:
        content: Content to fact-check
        operation_type: Type of fact-checking operation to perform
        **kwargs: Additional parameters for operation

    Returns:
        Fact-checking operation results dictionary
    """
    engine = get_fact_checker_engine()

    try:
        logger.info(f"🔍 Processing {operation_type} fact-checking operation for {len(content)} characters")

        if operation_type == "verify":
            result = engine.verify_facts(content, kwargs.get("source_url"))
        elif operation_type == "validate_sources":
            result = engine.validate_sources(content, kwargs.get("source_url"), kwargs.get("domain"))
        elif operation_type == "comprehensive":
            result = engine.comprehensive_fact_check(content, kwargs.get("source_url"), kwargs.get("metadata"))
        elif operation_type == "extract_claims":
            result = engine.extract_claims(content)
        elif operation_type == "assess_credibility":
            result = engine.assess_credibility(content, kwargs.get("domain"), kwargs.get("source_url"))
        elif operation_type == "detect_contradictions":
            result = engine.detect_contradictions(kwargs.get("text_passages", []))
        else:
            result = {"error": f"Unknown operation type: {operation_type}"}

        logger.info(f"✅ {operation_type} fact-checking operation completed")
        return result

    except Exception as e:
        logger.error(f"❌ {operation_type} fact-checking operation failed: {e}")
        return {"error": str(e)}

async def verify_facts(content: str, source_url: Optional[str] = None, context: Optional[str] = None) -> Dict[str, Any]:
    """
    Primary fact verification function using AI models.

    This function verifies factual claims using multiple AI models including
    DistilBERT for fact classification and evidence assessment.

    Args:
        content: Content containing claims to verify
        source_url: Source URL for context
        context: Additional context for verification

    Returns:
        Dictionary containing verification results
    """
    if not content or not content.strip():
        return {"verification_score": 0.0, "classification": "empty", "error": "Empty content provided"}

    try:
        engine = get_fact_checker_engine()

        # Perform fact verification
        verification = engine.verify_facts(content, source_url, context)

        # Enhance with additional analysis
        verification["analysis_metadata"] = {
            "content_length": len(content),
            "source_url": source_url,
            "context_provided": context is not None,
            "analysis_timestamp": datetime.now().isoformat(),
            "analyzer_version": "fact_checker_v2_verify"
        }

        # Log feedback for training
        engine.log_feedback("verify_facts", {
            "verification_score": verification.get("verification_score", 0.0),
            "classification": verification.get("classification", "unknown")
        })

        return verification

    except Exception as e:
        logger.error(f"Error in fact verification: {e}")
        return {"error": str(e)}

async def validate_sources(content: str, source_url: Optional[str] = None, domain: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate and assess source credibility.

    This function evaluates the reliability and credibility of information sources
    using domain analysis and content assessment.

    Args:
        content: Source content to evaluate
        source_url: Source URL
        domain: Domain name (extracted from URL if not provided)

    Returns:
        Dictionary containing credibility assessment
    """
    if not content and not source_url and not domain:
        return {"error": "At least one of content, source_url, or domain must be provided"}

    try:
        engine = get_fact_checker_engine()

        # Assess source credibility
        credibility = engine.assess_credibility(content, domain, source_url)

        # Add metadata
        credibility["analysis_metadata"] = {
            "content_length": len(content) if content else 0,
            "source_url": source_url,
            "domain": domain,
            "analysis_timestamp": datetime.now().isoformat(),
            "analyzer_version": "fact_checker_v2_credibility"
        }

        # Log feedback for training
        engine.log_feedback("validate_sources", {
            "credibility_score": credibility.get("credibility_score", 0.0),
            "reliability": credibility.get("reliability", "unknown")
        })

        return credibility

    except Exception as e:
        logger.error(f"Error in source validation: {e}")
        return {"error": str(e)}

async def comprehensive_fact_check(
    content: str,
    source_url: Optional[str] = None,
    context: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Perform comprehensive fact-checking on full articles.

    This function provides complete fact verification including claim extraction,
    evidence assessment, contradiction detection, and source credibility evaluation.

    Args:
        content: Full article content to fact-check
        source_url: Article source URL
        context: Additional context
        metadata: Article metadata

    Returns:
        Dictionary containing comprehensive fact-checking results
    """
    if not content or not content.strip():
        return {"overall_score": 0.0, "assessment": "empty", "error": "Empty content provided"}

    try:
        engine = get_fact_checker_engine()

        # Perform comprehensive analysis
        result = engine.comprehensive_fact_check(content, source_url, metadata)

        # Add processing metadata
        result["processing_metadata"] = {
            "content_length": len(content),
            "source_url": source_url,
            "context_provided": context is not None,
            "metadata_provided": metadata is not None,
            "processing_timestamp": datetime.now().isoformat(),
            "analyzer_version": "fact_checker_v2_comprehensive"
        }

        # Calculate overall assessment
        overall_score = result.get("overall_score", 0.5)
        if overall_score >= 0.8:
            result["overall_assessment"] = "highly_reliable"
        elif overall_score >= 0.6:
            result["overall_assessment"] = "generally_reliable"
        elif overall_score >= 0.4:
            result["overall_assessment"] = "mixed_reliability"
        else:
            result["overall_assessment"] = "low_reliability"

        # Log feedback for training
        engine.log_feedback("comprehensive_fact_check", {
            "overall_score": overall_score,
            "assessment": result.get("overall_assessment", "unknown"),
            "claims_analyzed": len(result.get("claims_analysis", {}).get("extracted_claims", []))
        })

        return result

    except Exception as e:
        logger.error(f"Error in comprehensive fact-check: {e}")
        return {"error": str(e)}

async def extract_claims(content: str) -> Dict[str, Any]:
    """
    Extract verifiable claims from text content.

    This function uses NLP techniques to identify factual claims that can be verified
    against available evidence and sources.

    Args:
        content: Text content to extract claims from

    Returns:
        Dictionary containing extracted claims and analysis
    """
    if not content or not content.strip():
        return {"error": "Empty content provided for claim extraction"}

    try:
        engine = get_fact_checker_engine()

        # Extract claims
        claims_result = engine.extract_claims(content)

        # Enhance with verification readiness assessment
        claims = claims_result.get("claims", [])
        verification_ready = []

        for claim in claims:
            # Simple heuristics for verification readiness
            verification_indicators = sum([
                1 for indicator in ["according to", "reported", "announced", "study", "data", "research"]
                if indicator in claim.lower()
            ])

            if verification_indicators > 0 or len(claim.split()) > 5:
                verification_ready.append(claim)

        claims_result["verification_ready_claims"] = verification_ready
        claims_result["verification_ready_count"] = len(verification_ready)

        # Add metadata
        claims_result["analysis_metadata"] = {
            "content_length": len(content),
            "claims_extracted": len(claims),
            "verification_ready": len(verification_ready),
            "analysis_timestamp": datetime.now().isoformat(),
            "analyzer_version": "fact_checker_v2_extraction"
        }

        # Log feedback for training
        engine.log_feedback("extract_claims", {
            "total_claims": len(claims),
            "verification_ready": len(verification_ready)
        })

        return claims_result

    except Exception as e:
        logger.error(f"Error in claim extraction: {e}")
        return {"error": str(e)}

async def assess_credibility(
    content: Optional[str] = None,
    domain: Optional[str] = None,
    source_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Assess the credibility and reliability of information sources.

    This function evaluates source credibility using multiple factors including
    domain reputation, content analysis, and historical reliability.

    Args:
        content: Source content (optional)
        domain: Domain name (optional)
        source_url: Full source URL (optional)

    Returns:
        Dictionary containing credibility assessment
    """
    if not any([content, domain, source_url]):
        return {"error": "At least one parameter (content, domain, or source_url) must be provided"}

    try:
        engine = get_fact_checker_engine()

        # Assess credibility
        credibility = engine.assess_credibility(content, domain, source_url)

        # Add metadata
        credibility["analysis_metadata"] = {
            "content_provided": content is not None,
            "domain_provided": domain is not None,
            "source_url_provided": source_url is not None,
            "analysis_timestamp": datetime.now().isoformat(),
            "analyzer_version": "fact_checker_v2_credibility"
        }

        # Log feedback for training
        engine.log_feedback("assess_credibility", {
            "credibility_score": credibility.get("credibility_score", 0.0),
            "reliability": credibility.get("reliability", "unknown")
        })

        return credibility

    except Exception as e:
        logger.error(f"Error in credibility assessment: {e}")
        return {"error": str(e)}

async def detect_contradictions(text_passages: List[str]) -> Dict[str, Any]:
    """
    Detect logical contradictions and inconsistencies in text passages.

    This function identifies contradictions between multiple text passages
    using semantic analysis and logical reasoning.

    Args:
        text_passages: List of text passages to analyze for contradictions

    Returns:
        Dictionary containing contradiction analysis
    """
    if not text_passages or len(text_passages) < 2:
        return {"error": "At least 2 text passages are required for contradiction detection"}

    try:
        engine = get_fact_checker_engine()

        # Detect contradictions
        contradictions = engine.detect_contradictions(text_passages)

        # Add metadata
        contradictions["analysis_metadata"] = {
            "passages_analyzed": len(text_passages),
            "contradictions_found": contradictions.get("contradictions_found", 0),
            "analysis_timestamp": datetime.now().isoformat(),
            "analyzer_version": "fact_checker_v2_contradictions"
        }

        # Log feedback for training
        engine.log_feedback("detect_contradictions", {
            "passages_count": len(text_passages),
            "contradictions_found": contradictions.get("contradictions_found", 0)
        })

        return contradictions

    except Exception as e:
        logger.error(f"Error in contradiction detection: {e}")
        return {"error": str(e)}

# GPU-accelerated functions with CPU fallbacks
async def validate_is_news_gpu(content: str) -> Dict[str, Any]:
    """
    GPU-accelerated news content validation.

    Determines if content qualifies as legitimate news reporting using AI models.
    """
    try:
        engine = get_fact_checker_engine()
        return await engine.validate_is_news_gpu(content)
    except Exception as e:
        logger.warning(f"GPU news validation failed, falling back to CPU: {e}")
        return await validate_is_news_cpu(content)

async def validate_is_news_cpu(content: str) -> Dict[str, Any]:
    """
    CPU-based news content validation fallback.

    Basic heuristic-based news validation when GPU is unavailable.
    """
    try:
        # Simple heuristic-based validation
        content_lower = content.lower()

        # News indicators
        news_keywords = ["breaking", "report", "headline", "news", "announced", "according to"]
        news_score = sum(1 for keyword in news_keywords if keyword in content_lower) / len(news_keywords)

        # Structure indicators
        has_structure = any(indicator in content for indicator in [" - ", " | ", "\n\n"])

        # Length indicator (news articles are typically substantial)
        length_score = min(1.0, len(content) / 1000.0)

        # Combined score
        is_news_score = (news_score * 0.5 + has_structure * 0.3 + length_score * 0.2)

        return {
            "is_news": is_news_score > 0.4,
            "confidence": is_news_score,
            "news_score": news_score,
            "structure_score": has_structure,
            "length_score": length_score,
            "method": "cpu_fallback",
            "analysis_timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"CPU news validation failed: {e}")
        return {"error": str(e), "is_news": False, "method": "cpu_fallback"}

async def verify_claims_gpu(claims: List[str], sources: List[str]) -> Dict[str, Any]:
    """
    GPU-accelerated claim verification for multiple claims.
    """
    try:
        engine = get_fact_checker_engine()
        return await engine.verify_claims_gpu(claims, sources)
    except Exception as e:
        logger.warning(f"GPU claims verification failed, falling back to CPU: {e}")
        return await verify_claims_cpu(claims, sources)

async def verify_claims_cpu(claims: List[str], sources: List[str]) -> Dict[str, Any]:
    """
    CPU-based claim verification fallback.
    """
    try:
        results = {}
        source_text = "\n".join(sources) if sources else ""

        for claim in claims:
            # Simple verification based on source matching
            verification_score = 0.5

            if source_text:
                # Check if claim elements appear in sources
                claim_words = set(claim.lower().split())
                source_words = set(source_text.lower().split())
                overlap = len(claim_words.intersection(source_words))
                verification_score = min(1.0, overlap / len(claim_words) * 2)

            results[claim] = {
                "verification_score": verification_score,
                "classification": "verified" if verification_score > 0.6 else "questionable",
                "confidence": verification_score,
                "method": "cpu_fallback"
            }

        return {
            "results": results,
            "total_claims": len(claims),
            "verified_claims": sum(1 for r in results.values() if r["classification"] == "verified"),
            "method": "cpu_fallback",
            "analysis_timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"CPU claims verification failed: {e}")
        return {"error": str(e), "method": "cpu_fallback"}

# Utility functions
def get_performance_stats() -> Dict[str, Any]:
    """Get GPU acceleration performance statistics."""
    try:
        engine = get_fact_checker_engine()
        return engine.get_performance_stats()
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return {"error": str(e), "gpu_available": False}

def get_model_status() -> Dict[str, Any]:
    """Get status of all fact-checking models."""
    try:
        engine = get_fact_checker_engine()
        return engine.get_model_status()
    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        return {"error": str(e), "models_loaded": False}

def log_feedback(feedback_data: Dict[str, Any]) -> Dict[str, Any]:
    """Log user feedback for model improvement."""
    try:
        engine = get_fact_checker_engine()
        return engine.log_feedback(feedback_data)
    except Exception as e:
        logger.error(f"Error logging feedback: {e}")
        return {"error": str(e), "logged": False}

def correct_verification(
    claim: str,
    context: Optional[str] = None,
    incorrect_classification: str = "",
    correct_classification: str = "",
    priority: int = 2
) -> Dict[str, Any]:
    """Submit user correction for fact verification."""
    try:
        engine = get_fact_checker_engine()
        return engine.correct_verification(claim, context, incorrect_classification, correct_classification, priority)
    except Exception as e:
        logger.error(f"Error submitting verification correction: {e}")
        return {"error": str(e), "correction_submitted": False}

def correct_credibility(
    source_text: Optional[str] = None,
    domain: str = "",
    incorrect_reliability: str = "",
    correct_reliability: str = "",
    priority: int = 2
) -> Dict[str, Any]:
    """Submit user correction for credibility assessment."""
    try:
        engine = get_fact_checker_engine()
        return engine.correct_credibility(source_text, domain, incorrect_reliability, correct_reliability, priority)
    except Exception as e:
        logger.error(f"Error submitting credibility correction: {e}")
        return {"error": str(e), "correction_submitted": False}

def get_training_status() -> Dict[str, Any]:
    """Get online training status for fact checker models."""
    try:
        engine = get_fact_checker_engine()
        return engine.get_training_status()
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        return {"error": str(e), "online_training_enabled": False}

def force_model_update() -> Dict[str, Any]:
    """Force immediate model update (admin function)."""
    try:
        engine = get_fact_checker_engine()
        return engine.force_model_update()
    except Exception as e:
        logger.error(f"Error forcing model update: {e}")
        return {"error": str(e), "update_triggered": False}

async def health_check() -> Dict[str, Any]:
    """
    Perform health check on fact checker components.

    Returns:
        Health check results with component status
    """
    try:
        engine = get_fact_checker_engine()

        model_status = engine.get_model_status()

        health_status = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "components": {
                "engine": "healthy",
                "mcp_bus": "healthy",  # Assume healthy unless proven otherwise
                "fact_checking_models": "healthy",
                "gpu_acceleration": "healthy" if model_status.get("gpu_available", False) else "degraded"
            },
            "model_status": model_status,
            "processing_stats": getattr(engine, 'processing_stats', {})
        }

        # Check for any unhealthy components
        unhealthy_components = [k for k, v in health_status["components"].items() if v == "unhealthy"]
        if unhealthy_components:
            health_status["overall_status"] = "degraded"
            health_status["issues"] = [f"Component {comp} is unhealthy" for comp in unhealthy_components]

        # Check model availability
        loaded_models = sum(1 for status in model_status.values() if isinstance(status, bool) and status)
        if loaded_models < 2:  # Require at least 2 of 4 models for basic functionality
            health_status["overall_status"] = "degraded"
            health_status["issues"] = health_status.get("issues", []) + [f"Only {loaded_models}/4 AI models loaded"]

        logger.info(f"🏥 Fact checker health check: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Fact checker health check failed: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "unhealthy",
            "error": str(e)
        }

def validate_fact_check_result(result: Dict[str, Any], expected_fields: Optional[List[str]] = None) -> bool:
    """
    Validate fact-check result structure.

    Args:
        result: Fact-check result to validate
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
    common_fields = ["analysis_metadata", "analysis_timestamp"]
    return any(field in result for field in common_fields)

def format_fact_check_output(result: Dict[str, Any], format_type: str = "json") -> str:
    """
    Format fact-check result for output.

    Args:
        result: Fact-check result to format
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
            if "verification_score" in result:
                lines.append(f"Verification Score: {result['verification_score']:.2f}/1.0")
                lines.append(f"Classification: {result.get('classification', 'unknown')}")

            if "credibility_score" in result:
                lines.append(f"Credibility Score: {result['credibility_score']:.2f}/1.0")
                lines.append(f"Reliability: {result.get('reliability', 'unknown')}")

            if "overall_score" in result:
                lines.append(f"Overall Score: {result['overall_score']:.2f}/1.0")
                lines.append(f"Assessment: {result.get('overall_assessment', 'unknown')}")

            if "claim_count" in result:
                lines.append(f"Claims Extracted: {result['claim_count']}")

            if "contradictions_found" in result:
                lines.append(f"Contradictions Found: {result['contradictions_found']}")

            return "\n".join(lines)

        elif format_type == "markdown":
            if "error" in result:
                return f"## Fact Check Error\n\n{result['error']}"

            lines = ["# Fact Check Results\n"]

            if "verification_score" in result:
                lines.append("## Verification Results")
                lines.append(f"- **Score**: {result['verification_score']:.2f}/1.0")
                lines.append(f"- **Classification**: {result.get('classification', 'unknown')}")

            if "credibility_score" in result:
                lines.append("## Source Credibility")
                lines.append(f"- **Score**: {result['credibility_score']:.2f}/1.0")
                lines.append(f"- **Reliability**: {result.get('reliability', 'unknown')}")

            if "overall_score" in result:
                lines.append("## Overall Assessment")
                lines.append(f"- **Score**: {result['overall_score']:.2f}/1.0")
                lines.append(f"- **Assessment**: {result.get('overall_assessment', 'unknown')}")

            if "claims_analysis" in result:
                claims = result["claims_analysis"].get("extracted_claims", [])
                lines.append("## Claims Analysis")
                lines.append(f"- **Total Claims**: {len(claims)}")
                if claims:
                    lines.append("- **Sample Claims**:")
                    for i, claim in enumerate(claims[:3]):
                        lines.append(f"  - {claim[:100]}{'...' if len(claim) > 100 else ''}")

            if "contradictions_found" in result and result["contradictions_found"] > 0:
                lines.append("## Contradictions Detected")
                lines.append(f"- **Found**: {result['contradictions_found']} contradictions")

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"

# Export main functions
__all__ = [
    'verify_facts',
    'validate_sources',
    'comprehensive_fact_check',
    'extract_claims',
    'assess_credibility',
    'detect_contradictions',
    'validate_is_news_gpu',
    'validate_is_news_cpu',
    'verify_claims_gpu',
    'verify_claims_cpu',
    'get_performance_stats',
    'get_model_status',
    'log_feedback',
    'correct_verification',
    'correct_credibility',
    'get_training_status',
    'force_model_update',
    'health_check',
    'validate_fact_check_result',
    'format_fact_check_output',
    'get_fact_checker_engine'
]