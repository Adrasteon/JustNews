"""
Fact Checker V2 - Production-Ready Multi-Model AI Architecture
Focused fact verification with 4 specialized AI models

AI Models:
1. DistilBERT-base: Fact verification (factual/questionable classification)
2. RoBERTa-base: Source credibility assessment (reliability scoring)  
3. SentenceTransformers: Evidence retrieval (semantic search)
4. spaCy NER: Claim extraction (verifiable claims identification)

Note: Contradiction detection moved to Reasoning Agent (Nucleoid symbolic logic)
Performance: Production-ready with GPU acceleration
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

# Fallback configuration for legacy compatibility
MODEL_NAME = "distilgpt2"
MODEL_PATH = os.environ.get("MODEL_PATH", "./models/distilgpt2")
OPTIMIZED_MAX_LENGTH = 1512
OPTIMIZED_BATCH_SIZE = 16

# Environment configuration
FEEDBACK_LOG = os.environ.get("FACT_CHECKER_FEEDBACK_LOG", "./feedback_fact_checker.log")


logger = get_logger(__name__)

# Online Training Integration (deferred)
try:
    # Import training system symbols but DO NOT call initialize_online_training() here.
    # Initializing the online training coordinator can trigger DB connections / background
    # threads which we must avoid at import time (it can block test collection).
    from training_system import (
        add_training_feedback,
        add_user_correction,
        get_training_coordinator,
        initialize_online_training,
    )
    ONLINE_TRAINING_AVAILABLE = True
    # Defer actual initialization to runtime to avoid heavy side-effects during import/collection
    def _ensure_online_training_initialized():
        try:
            initialize_online_training(update_threshold=30)
            logger.info("🎓 Online Training enabled for Fact Checker V2 (initialized)")
        except Exception as _e:
            logger.warning("⚠️ Failed to initialize online training at runtime: %s", _e)

except ImportError:
    ONLINE_TRAINING_AVAILABLE = False
    logger.warning("⚠️ Online Training not available for Fact Checker V2")

# NOTE: Avoid initializing the heavy V2 engine at import time. Some callers (and pytest)
# import this module during collection; initializing models (transformers, spaCy,
# SentenceTransformers) here can trigger downloads and long-running operations.
# Provide a helper to initialize on-demand instead.
def ensure_fact_checker_engine_initialized():
    """Ensure the global Fact Checker V2 engine is initialized (runtime)."""
    try:
        if FACT_CHECKER_V2_AVAILABLE:
            # initialize_fact_checker_v2() may be expensive; call only when needed
            try:
                initialize_fact_checker_v2()
                logger.info("🚀 Fact Checker V2 Engine initialized (deferred)")
            except Exception as e:
                logger.warning("Failed to initialize Fact Checker V2 Engine at runtime: %s", e)
        else:
            logger.warning("⚠️ Running in fallback mode - V2 engine unavailable")
    except NameError:
        # initialize_fact_checker_v2 not available in scope; ignore
        logger.debug("initialize_fact_checker_v2 not available; skipping deferred init")

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
        # Ensure runtime initialization when first needed
        if 'ensure_fact_checker_engine_initialized' in globals():
            try:
                ensure_fact_checker_engine_initialized()
            except Exception:
                pass

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

                # Online Training: Add prediction feedback for continuous improvement
                if ONLINE_TRAINING_AVAILABLE and ' _ensure_online_training_initialized' not in globals():
                    # If available, ensure online training is initialized at runtime before using it
                    try:
                        _ensure_online_training_initialized()
                    except Exception:
                        pass
                if ONLINE_TRAINING_AVAILABLE:
                    try:
                        verification_confidence = verification.get("confidence", 0.5)
                        credibility_confidence = credibility.get("confidence", 0.5)
                        avg_confidence = (verification_confidence + credibility_confidence) / 2
                        # Add training feedback (actual_output would come from user feedback)
                        add_training_feedback(
                            agent_name="fact_checker",
                            task_type="fact_verification",
                            input_text=claim,
                            predicted_output=verification.get("classification", "unknown"),
                            actual_output=verification.get("classification", "unknown"),  # This would be corrected by user feedback
                            confidence=avg_confidence
                        )
                    except Exception as _e:
                        logger.debug("Online training feedback submission failed: %s", _e)

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
        # Ensure runtime initialization when first needed
        if 'ensure_fact_checker_engine_initialized' in globals():
            try:
                ensure_fact_checker_engine_initialized()
            except Exception:
                pass

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


def to_neural_assessment(comprehensive_result: dict) -> dict:
    """Convert a comprehensive_fact_check result into the standardized NeuralAssessment dict.

    This is a helper so the Fact Checker can produce the shared schema used by reasoning.
    """
    try:
        # Normalize extracted_claims to a list of strings (claim texts)
        raw_claims = comprehensive_result.get("claims_analysis", {}).get("extracted_claims", [])
        normalized_claims = []
        for c in raw_claims:
            if isinstance(c, dict):
                # prefer explicit 'text' field, then 'claim' or fallback to str()
                text = c.get("text") or c.get("claim") or str(c)
                normalized_claims.append(text)
            else:
                normalized_claims.append(str(c))

        assessment = {
            "version": "1.0",
            "confidence": float(comprehensive_result.get("overall_score", 0.5)),
            "source_credibility": float(comprehensive_result.get("credibility_assessment", {}).get("credibility_score", 0.5) if comprehensive_result.get("credibility_assessment") else 0.5),
            "extracted_claims": normalized_claims,
            "evidence_matches": comprehensive_result.get("evidence_matches", []),
            "processing_metadata": {
                "models_used": comprehensive_result.get("models_used", []),
                "timestamp": comprehensive_result.get("processing_timestamp") or comprehensive_result.get("timestamp")
            }
        }
        return assessment
    except Exception as e:
        logger.warning(f"Failed to convert to neural assessment: {e}")
        return {
            "version": "1.0",
            "confidence": 0.5,
            "source_credibility": 0.5,
            "extracted_claims": [],
            "evidence_matches": [],
            "processing_metadata": {}
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

def _fallback_comprehensive_fact_check(article_text: str, source_url: str, metadata: dict | None = None) -> dict:
    """Fallback comprehensive fact-checking"""
    return {
        "overall_score": 0.5,
        "assessment": "unknown",
        "claims_analysis": {"extracted_claims": [], "claim_count": 0},
        "article_metadata": metadata or {},
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

# Online Training Functions
def correct_fact_verification(claim: str,
                            context: str,
                            incorrect_classification: str,
                            correct_classification: str,
                            priority: int = 2) -> dict:
    """
    Submit user correction for fact verification to improve model accuracy
    
    Args:
        claim: The factual claim that was incorrectly classified
        context: Additional context for the claim
        incorrect_classification: What the model predicted (e.g., "factual", "questionable")
        correct_classification: What the correct classification should be
        priority: Correction priority (0=low, 1=medium, 2=high, 3=critical)
        
    Returns:
        Confirmation of correction submission
    """
    try:
        if ONLINE_TRAINING_AVAILABLE:
            add_user_correction(
                agent_name="fact_checker",
                task_type="fact_verification",
                input_text=claim,
                incorrect_output=incorrect_classification,
                correct_output=correct_classification,
                priority=priority
            )

            result = {
                "correction_submitted": True,
                "claim": claim,
                "incorrect_classification": incorrect_classification,
                "correct_classification": correct_classification,
                "priority": priority,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "immediate_update": priority >= 2
            }

            log_feedback("user_correction_fact_verification", result)

            logger.info(f"📝 Fact verification correction submitted: "
                       f"'{incorrect_classification}' → '{correct_classification}' (Priority: {priority})")

            return result
        else:
            return {
                "correction_submitted": False,
                "error": "Online training not available",
                "fallback": True
            }

    except Exception as e:
        logger.error(f"Failed to submit fact verification correction: {e}")
        return {
            "correction_submitted": False,
            "error": str(e)
        }

def correct_credibility_assessment(source_text: str,
                                  domain: str,
                                  incorrect_reliability: str,
                                  correct_reliability: str,
                                  priority: int = 2) -> dict:
    """
    Submit user correction for source credibility assessment
    
    Args:
        source_text: The source content that was incorrectly assessed
        domain: Domain name of the source
        incorrect_reliability: What the model predicted (e.g., "high", "medium", "low")
        correct_reliability: What the correct reliability should be
        priority: Correction priority (0=low, 1=medium, 2=high, 3=critical)
        
    Returns:
        Confirmation of correction submission
    """
    try:
        if ONLINE_TRAINING_AVAILABLE:
            add_user_correction(
                agent_name="fact_checker",
                task_type="credibility_assessment",
                input_text=f"Domain: {domain} - {source_text}",
                incorrect_output=incorrect_reliability,
                correct_output=correct_reliability,
                priority=priority
            )

            result = {
                "correction_submitted": True,
                "domain": domain,
                "incorrect_reliability": incorrect_reliability,
                "correct_reliability": correct_reliability,
                "priority": priority,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "immediate_update": priority >= 2
            }

            log_feedback("user_correction_credibility_assessment", result)

            logger.info(f"📝 Credibility assessment correction submitted for {domain}: "
                       f"'{incorrect_reliability}' → '{correct_reliability}' (Priority: {priority})")

            return result
        else:
            return {
                "correction_submitted": False,
                "error": "Online training not available",
                "fallback": True
            }

    except Exception as e:
        logger.error(f"Failed to submit credibility correction: {e}")
        return {
            "correction_submitted": False,
            "error": str(e)
        }

def get_online_training_status() -> dict:
    """Get current status of online training for Fact Checker"""
    try:
        if ONLINE_TRAINING_AVAILABLE:
            from training_system import get_online_training_status
            status = get_online_training_status()

            # Add Fact Checker specific information
            fact_checker_status = {
                "online_training_enabled": True,
                "fact_checker_buffer_size": status.get("buffer_sizes", {}).get("fact_checker", 0),
                "total_system_examples": status.get("total_examples", 0),
                "is_training": status.get("is_training", False),
                "update_threshold": 30,  # Fact checker specific threshold
                "v2_models": ["DistilBERT", "RoBERTa", "BERT-large", "SentenceTransformers", "spaCy"],
                "supported_corrections": [
                    "fact_verification",
                    "credibility_assessment",
                    "contradiction_detection",
                    "claim_extraction"
                ]
            }

            return {**status, **fact_checker_status}
        else:
            return {
                "online_training_enabled": False,
                "reason": "Online training coordinator not available"
            }

    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        return {
            "online_training_enabled": False,
            "error": str(e)
        }

def force_fact_checker_update() -> dict:
    """Force immediate model update for Fact Checker (admin function)"""
    try:
        if ONLINE_TRAINING_AVAILABLE:
            coordinator = get_training_coordinator()
            if coordinator:
                success = coordinator.force_update_agent("fact_checker")

                result = {
                    "update_triggered": success,
                    "agent": "fact_checker",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "immediate": True
                }

                log_feedback("force_model_update", result)

                if success:
                    logger.info("🚀 Forced Fact Checker model update initiated")
                else:
                    logger.warning("⚠️ Failed to trigger Fact Checker model update (system may be busy)")

                return result
            else:
                return {
                    "update_triggered": False,
                    "error": "Training coordinator not available"
                }
        else:
            return {
                "update_triggered": False,
                "error": "Online training not available"
            }

    except Exception as e:
        logger.error(f"Failed to force model update: {e}")
        return {
            "update_triggered": False,
            "error": str(e)
        }
