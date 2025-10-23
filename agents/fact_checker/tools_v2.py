"""
Fact Checker V2 - Production-Ready Multi-Model AI Architecture
Specialized fact verification with 5 AI models matching Scout V2 standard

AI Models:
1. DistilBERT-base: Fact verification (factual/questionable classification)
2. RoBERTa-base: Source credibility assessment (reliability scoring)  
3. BERT-large: Contradiction detection (logical consistency)
4. SentenceTransformers: Evidence retrieval (semantic search)
5. spaCy NER: Claim extraction (verifiable claims identification)

Performance: Production-ready with GPU acceleration and professional error handling
V4 Compliance: TensorRT-ready multi-model architecture with MCP bus integration
Dependencies: transformers, sentence-transformers, spacy, torch, numpy
"""

import json
import os
from datetime import datetime, timezone

from common.observability import get_logger

# Import V2 Engine
try:
    from agents.fact_checker.fact_checker_v2_engine import (
        get_fact_checker_engine,
        initialize_fact_checker_v2,
    )
    FACT_CHECKER_V2_AVAILABLE = True
except ImportError as e:
    FACT_CHECKER_V2_AVAILABLE = False
    logging.error(f"❌ Fact Checker V2 Engine not available: {e}")

# Fallback imports for compatibility
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
except ImportError:
    AutoModelForCausalLM = None
    AutoTokenizer = None
    pipeline = None

# Environment configuration
FEEDBACK_LOG = os.environ.get("FACT_CHECKER_FEEDBACK_LOG", "./feedback_fact_checker.log")

# Fallback configuration for legacy compatibility (GPT-2 Medium - Modern replacement for deprecated DialoGPT)
# Use environment override FACT_CHECKER_CONVERSATIONAL_MODEL; default to a small, task-specific model
MODEL_NAME = os.environ.get("FACT_CHECKER_CONVERSATIONAL_MODEL", "gpt2-medium")
MODEL_PATH = os.environ.get("MODEL_PATH", "./models/" + MODEL_NAME.replace('/', '_'))
OPTIMIZED_MAX_LENGTH = 1512
OPTIMIZED_BATCH_SIZE = 16


logger = get_logger(__name__)

# Initialize V2 Engine on module load
if FACT_CHECKER_V2_AVAILABLE:
    initialize_fact_checker_v2()
    logger.info("🚀 Fact Checker V2 Engine initialized with 5 AI models")
else:
    logger.warning("⚠️ Running in fallback mode - V2 engine unavailable")

def log_feedback(event: str, details: dict):
    """Universal feedback logging for Fact Checker operations"""
    with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
        timestamp = datetime.now(timezone.utc).isoformat()
        f.write(f"{timestamp}\t{event}\t{json.dumps(details)}\n")

def verify_claim(claim: str, context: str = "", source_url: str = "") -> dict:
    """
    V2 Fact Verification using 5 specialized AI models
    
    Args:
        claim: The factual claim to verify
        context: Additional context for verification
        source_url: URL of the source (for credibility assessment)
        
    Returns:
        Comprehensive fact-check analysis with verification scores
    """
    try:
        if FACT_CHECKER_V2_AVAILABLE:
            # Use V2 Engine with 5 AI models
            engine = get_fact_checker_engine()
            if engine:
                # Primary fact verification
                verification = engine.verify_fact(claim, context)

                # Source credibility assessment
                domain = source_url.split('/')[2] if source_url and '/' in source_url else ""
                credibility = engine.assess_source_credibility(context[:500], domain)

                result = {
                    "verification_result": verification,
                    "credibility_assessment": credibility,
                    "claim": claim,
                    "context": context[:200] + "..." if len(context) > 200 else context,
                    "source_url": source_url,
                    "v2_analysis": True,
                    "models_used": ["distilbert", "roberta"],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                log_feedback("claim_verified_v2", {
                    "verification_score": verification.get("verification_score", 0.5),
                    "credibility_score": credibility.get("credibility_score", 0.5),
                    "classification": verification.get("classification", "unknown")
                })

                return result

        # Fallback to basic verification
        return _fallback_verify_claim(claim, context, source_url)

    except Exception as e:
        logger.error(f"Claim verification error: {e}")
        return {
            "verification_result": {"verification_score": 0.5, "classification": "error"},
            "credibility_assessment": {"credibility_score": 0.5, "reliability": "error"},
            "error": str(e),
            "v2_analysis": False
        }

def comprehensive_fact_check(article_text: str, source_url: str = "", metadata: dict | None = None) -> dict:
    """
    V2 Comprehensive Fact-Checking using all 5 AI models
    
    Args:
        article_text: Full article text to fact-check
        source_url: URL of the article source
        metadata: Additional article metadata
        
    Returns:
        Complete fact-checking analysis with multiple model outputs
    """
    try:
        if FACT_CHECKER_V2_AVAILABLE:
            # Use V2 Engine comprehensive analysis
            engine = get_fact_checker_engine()
            if engine:
                result = engine.comprehensive_fact_check(article_text, source_url)

                # Add metadata
                result["article_metadata"] = metadata or {}
                result["article_length"] = len(article_text)
                result["processing_timestamp"] = datetime.now(timezone.utc).isoformat()

                log_feedback("comprehensive_fact_check_v2", {
                    "overall_score": result.get("overall_score", 0.5),
                    "assessment": result.get("assessment", "unknown"),
                    "claims_count": len(result.get("claims_analysis", {}).get("extracted_claims", [])),
                    "contradictions_found": len(result.get("contradictions", []))
                })

                return result

        # Fallback to basic fact-checking
        return _fallback_comprehensive_fact_check(article_text, source_url, metadata)

    except Exception as e:
        logger.error(f"Comprehensive fact-check error: {e}")
        return {
            "overall_score": 0.5,
            "assessment": "error",
            "error": str(e),
            "v2_analysis": False
        }

def detect_contradictions(text_passages: list[str]) -> dict:
    """
    V2 Contradiction Detection using BERT-large
    
    Args:
        text_passages: List of text passages to check for contradictions
        
    Returns:
        Contradiction analysis with detected conflicts
    """
    try:
        if FACT_CHECKER_V2_AVAILABLE and len(text_passages) >= 2:
            engine = get_fact_checker_engine()
            if engine:
                contradictions = []

                # Check all pairs of passages
                for i in range(len(text_passages)):
                    for j in range(i + 1, len(text_passages)):
                        contradiction = engine.detect_contradictions(
                            text_passages[i],
                            text_passages[j]
                        )

                        if contradiction.get("status") == "contradiction":
                            contradictions.append({
                                "passage_a_index": i,
                                "passage_b_index": j,
                                "passage_a": text_passages[i][:100] + "...",
                                "passage_b": text_passages[j][:100] + "...",
                                "contradiction_score": contradiction.get("contradiction_score", 0.0),
                                "confidence": contradiction.get("confidence", 0.0)
                            })

                result = {
                    "contradictions_found": len(contradictions),
                    "contradictions": contradictions,
                    "passages_analyzed": len(text_passages),
                    "model_used": "bert-large-contradiction-detection",
                    "v2_analysis": True
                }

                log_feedback("contradiction_detection_v2", {
                    "passages_count": len(text_passages),
                    "contradictions_found": len(contradictions)
                })

                return result

        # Fallback basic contradiction detection
        return {
            "contradictions_found": 0,
            "contradictions": [],
            "passages_analyzed": len(text_passages),
            "model_used": "fallback",
            "v2_analysis": False
        }

    except Exception as e:
        logger.error(f"Contradiction detection error: {e}")
        return {
            "contradictions_found": 0,
            "contradictions": [],
            "error": str(e),
            "v2_analysis": False
        }

def extract_verifiable_claims(text: str) -> dict:
    """
    V2 Claim Extraction using spaCy NER + custom patterns
    
    Args:
        text: Text to extract verifiable claims from
        
    Returns:
        Extracted claims with entities and verification potential
    """
    try:
        if FACT_CHECKER_V2_AVAILABLE:
            engine = get_fact_checker_engine()
            if engine:
                result = engine.extract_claims(text)

                # Enhance with verification readiness assessment
                result["verification_ready_claims"] = []
                for claim in result.get("claims", []):
                    # Simple heuristics for verification readiness
                    verification_indicators = sum([
                        1 for indicator in ["according to", "reported", "announced", "study", "data"]
                        if indicator in claim.lower()
                    ])

                    if verification_indicators > 0 or len(claim.split()) > 5:
                        result["verification_ready_claims"].append(claim)

                result["v2_analysis"] = True

                log_feedback("claims_extraction_v2", {
                    "total_claims": result.get("claim_count", 0),
                    "entities_found": len(result.get("entities", [])),
                    "verification_ready": len(result["verification_ready_claims"])
                })

                return result

        # Fallback basic claim extraction
        return _fallback_extract_claims(text)

    except Exception as e:
        logger.error(f"Claim extraction error: {e}")
        return {
            "claims": [],
            "entities": [],
            "claim_count": 0,
            "error": str(e),
            "v2_analysis": False
        }

def assess_source_credibility(source_text: str, domain: str = "") -> dict:
    """
    V2 Source Credibility Assessment using RoBERTa
    
    Args:
        source_text: Text content from the source
        domain: Domain name of the source
        
    Returns:
        Credibility assessment with reliability scoring
    """
    try:
        if FACT_CHECKER_V2_AVAILABLE:
            engine = get_fact_checker_engine()
            if engine:
                result = engine.assess_source_credibility(source_text, domain)

                log_feedback("credibility_assessment_v2", {
                    "domain": domain,
                    "credibility_score": result.get("credibility_score", 0.5),
                    "reliability": result.get("reliability", "unknown")
                })

                return result

        # Fallback basic credibility assessment
        return _fallback_assess_credibility(source_text, domain)

    except Exception as e:
        logger.error(f"Credibility assessment error: {e}")
        return {
            "credibility_score": 0.5,
            "reliability": "error",
            "error": str(e),
            "v2_analysis": False
        }

def get_model_status() -> dict:
    """Get status of all Fact Checker V2 models"""
    try:
        if FACT_CHECKER_V2_AVAILABLE:
            engine = get_fact_checker_engine()
            if engine:
                return engine.get_model_info()

        return {
            "status": "fallback_mode",
            "v2_available": False,
            "reason": "V2 engine not available"
        }

    except Exception as e:
        logger.error(f"Model status error: {e}")
        return {"status": "error", "error": str(e)}

# Fallback functions for legacy compatibility
def _fallback_verify_claim(claim: str, context: str, source_url: str) -> dict:
    """Fallback claim verification using basic patterns"""
    # Simple heuristic-based verification
    confidence = 0.6 if any(indicator in claim.lower() for indicator in [
        "according to", "reported", "announced", "confirmed"
    ]) else 0.4

    return {
        "verification_result": {
            "verification_score": confidence,
            "classification": "unknown",
            "confidence": confidence
        },
        "credibility_assessment": {
            "credibility_score": 0.5,
            "reliability": "unknown",
            "confidence": 0.5
        },
        "v2_analysis": False,
        "fallback": True
    }

def _fallback_comprehensive_fact_check(article_text: str, source_url: str, metadata: dict | None) -> dict:
    """Fallback comprehensive fact-checking"""
    return {
        "overall_score": 0.5,
        "assessment": "unknown",
        "claims_analysis": {"extracted_claims": [], "claim_count": 0},
        "v2_analysis": False,
        "fallback": True
    }

def _fallback_extract_claims(text: str) -> dict:
    """Fallback claim extraction using basic patterns"""
    import re

    sentences = re.split(r'[.!?]+', text)
    claims = [
        sent.strip() for sent in sentences
        if any(indicator in sent.lower() for indicator in [
            "according to", "reported", "announced", "said", "claimed"
        ])
    ]

    return {
        "claims": claims[:5],
        "entities": [],
        "claim_count": len(claims),
        "v2_analysis": False,
        "fallback": True
    }

def _fallback_assess_credibility(source_text: str, domain: str) -> dict:
    """Fallback credibility assessment"""
    # Basic domain-based heuristics
    trusted_indicators = ["bbc", "reuters", "ap", "npr", "pbs"]

    if any(indicator in domain.lower() for indicator in trusted_indicators):
        credibility = 0.8
        reliability = "high"
    else:
        credibility = 0.5
        reliability = "unknown"

    return {
        "credibility_score": credibility,
        "reliability": reliability,
        "confidence": 0.5,
        "v2_analysis": False,
        "fallback": True
    }

# Legacy function for backward compatibility
def get_dialog_model():
    """Legacy function - maintained for backward compatibility"""
    if AutoModelForCausalLM is None or AutoTokenizer is None:
        raise ImportError("transformers library is not installed.")

    if not os.path.exists(MODEL_PATH) or not os.listdir(MODEL_PATH):
        print(f"Downloading {MODEL_NAME} to {MODEL_PATH}...")
        model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, cache_dir=MODEL_PATH)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=MODEL_PATH)
    else:
        print(f"Loading {MODEL_NAME} from local cache {MODEL_PATH}...")
        model = AutoModelForCausalLM.from_pretrained(MODEL_PATH)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

    return model, tokenizer

def check_claims(article: str, source: str) -> dict:
    """
    Legacy function - enhanced with V2 capabilities
    """
    return comprehensive_fact_check(article, source)

def validate_is_news(content: str) -> bool:
    """Validate if the given content qualifies as news."""
    logger.info(f"Validating content for news: {content[:50]}...")
    keywords = ["breaking", "report", "headline", "news"]
    is_news = any(keyword in content.lower() for keyword in keywords)
    log_feedback("validate_is_news", {"content": content[:100], "is_news": is_news})
    return is_news

def verify_claims(claims: list[str], sources: list[str]) -> dict:
    """Enhanced legacy function with V2 capabilities"""
    logger.info(f"Verifying {len(claims)} claims with {len(sources)} sources")

    results = {}
    for claim in claims:
        verification = verify_claim(claim, "\n".join(sources))
        results[claim] = verification.get("verification_result", {}).get("classification", "unknown")

    log_feedback("verify_claims", {"claims_count": len(claims), "sources_count": len(sources)})
    return results
