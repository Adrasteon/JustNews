"""
Critic Agent V2 - Specialized Logical Analysis Tools
Production-ready implementation with zero warnings and clean imports

SPECIALIZATION FOCUS:
1. Argument Structure Analysis - Identifying premises, conclusions, logical flow
2. Editorial Consistency - Checking for internal contradictions, coherence  
3. Logical Fallacy Detection - Identifying logical errors and weak reasoning
4. Source Credibility Assessment - Evaluating evidence quality and sourcing

NOTE: Sentiment and bias analysis have been centralized in Scout V2 Agent.
Use Scout V2 for all sentiment/bias analysis.
"""


import os
import re
import statistics
from datetime import datetime
from typing import Any, Dict, List

from common.observability import get_logger

# Configure logging

logger = get_logger(__name__)

# Feedback logging pattern
FEEDBACK_LOG = os.path.join(os.path.dirname(__file__), "critic_feedback.log")

def log_feedback(event: str, details: dict[str, Any]) -> None:
    """Universal feedback logging for Critic Agent V2."""
    try:
        feedback_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "agent": "critic_v2",
            "details": details
        }

        with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
            f.write(f"{feedback_entry}\n")

        logger.info(f"📝 Feedback logged: {event}")
    except Exception as e:
        logger.error(f"❌ Feedback logging failed: {e}")

# =============================================================================
# SPECIALIZED LOGICAL ANALYSIS FUNCTIONS
# =============================================================================

def analyze_argument_structure(text: str, url: str = None) -> dict[str, Any]:
    """
    Analyze the logical structure of arguments in text content.
    
    Args:
        text (str): Content to analyze for argument structure
        url (str, optional): Source URL for context
        
    Returns:
        Dict containing argument analysis including premises, conclusions,
        logical flow, and argument strength assessment
    """
    try:
        logger.info(f"🧠 Analyzing argument structure for {len(text)} characters")

        # Extract logical connectors and argument indicators
        premises = _extract_premises(text)
        conclusions = _extract_conclusions(text)
        logical_flow = _analyze_logical_flow(text)
        argument_strength = _assess_argument_strength(text, premises, conclusions)

        analysis = {
            "premises": premises,
            "conclusions": conclusions,
            "logical_flow": logical_flow,
            "argument_strength": argument_strength,
            "structural_analysis": {
                "premise_conclusion_ratio": len(premises) / max(len(conclusions), 1),
                "logical_connectors_count": len(logical_flow.get("connectors", [])),
                "argument_complexity": _calculate_argument_complexity(premises, conclusions),
                "coherence_score": _calculate_coherence_score(text)
            },
            "analysis_metadata": {
                "text_length": len(text),
                "url": url,
                "analysis_time": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_argument_structure"
            }
        }

        logger.info(f"✅ Argument analysis complete: {len(premises)} premises, {len(conclusions)} conclusions")
        return analysis

    except Exception as e:
        logger.error(f"❌ Error in argument structure analysis: {e}")
        return {"error": str(e)}
    
    finally:
        # Collect prediction for training
        try:
            confidence = min(0.95, max(0.5, analysis.get("argument_strength", {}).get("strength_score", 0.5)))
            from training_system import collect_prediction
            collect_prediction(
                agent_name="critic",
                task_type="argument_structure_analysis",
                input_text=text,
                prediction=analysis,
                confidence=confidence,
                source_url=url or ""
            )
            logger.debug(f"📊 Training data collected for argument analysis (confidence: {confidence:.3f})")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

def assess_editorial_consistency(text: str, url: str = None) -> dict[str, Any]:
    """Assess editorial consistency and internal coherence."""
    try:
        logger.info(f"📝 Assessing editorial consistency for {len(text)} characters")
        contradictions = _detect_contradictions(text)
        coherence_score = _calculate_coherence_score(text)
        
        result = {
            "contradictions": contradictions,
            "coherence_score": coherence_score,
            "consistency_score": max(0, 1.0 - len(contradictions) * 0.2),
            "analysis_time": datetime.now().isoformat()
        }
        
        return result
    except Exception as e:
        logger.error(f"❌ Error in editorial consistency: {e}")
        return {"error": str(e)}
    
    finally:
        # Collect prediction for training
        try:
            confidence = min(0.95, max(0.5, result.get("consistency_score", 0.5)))
            from training_system import collect_prediction
            collect_prediction(
                agent_name="critic",
                task_type="editorial_consistency_analysis",
                input_text=text,
                prediction=result,
                confidence=confidence,
                source_url=url or ""
            )
            logger.debug(f"📊 Training data collected for consistency analysis (confidence: {confidence:.3f})")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

def detect_logical_fallacies(text: str, url: str = None) -> dict[str, Any]:
    """Detect logical fallacies and reasoning errors."""
    try:
        logger.info(f"🕵️ Detecting logical fallacies in {len(text)} characters")
        fallacies = _detect_common_fallacies(text)
        
        result = {
            "fallacies_detected": fallacies,
            "fallacy_count": len(fallacies),
            "logical_strength": max(0, 1.0 - len(fallacies) * 0.3),
            "analysis_time": datetime.now().isoformat()
        }
        
        return result
    except Exception as e:
        logger.error(f"❌ Error in fallacy detection: {e}")
        return {"error": str(e)}
    
    finally:
        # Collect prediction for training
        try:
            confidence = min(0.95, max(0.5, result.get("logical_strength", 0.5)))
            from training_system import collect_prediction
            collect_prediction(
                agent_name="critic",
                task_type="logical_fallacy_detection",
                input_text=text,
                prediction=result,
                confidence=confidence,
                source_url=url or ""
            )
            logger.debug(f"📊 Training data collected for fallacy detection (confidence: {confidence:.3f})")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

def assess_source_credibility(text: str, url: str = None) -> dict[str, Any]:
    """Assess source credibility and evidence quality."""
    try:
        logger.info(f"📚 Assessing source credibility for {len(text)} characters")
        citations = _extract_citations(text)
        
        result = {
            "citations": citations,
            "citation_count": len(citations),
            "credibility_score": min(1.0, len(citations) * 0.2),
            "analysis_time": datetime.now().isoformat()
        }
        
        return result
    except Exception as e:
        logger.error(f"❌ Error in credibility assessment: {e}")
        return {"error": str(e)}
    
    finally:
        # Collect prediction for training
        try:
            confidence = min(0.95, max(0.5, result.get("credibility_score", 0.5)))
            from training_system import collect_prediction
            collect_prediction(
                agent_name="critic",
                task_type="source_credibility_assessment",
                input_text=text,
                prediction=result,
                confidence=confidence,
                source_url=url or ""
            )
            logger.debug(f"📊 Training data collected for credibility assessment (confidence: {confidence:.3f})")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

def critique_synthesis(content: str, url: str = None) -> Dict[str, Any]:
    """
    Synthesize comprehensive content critique using all available analysis tools
    
    Args:
        content (str): Content to critique
        url (str, optional): Source URL for context
        
    Returns:
        Dict containing comprehensive critique analysis
    """
    try:
        logger.info(f"🔍 Synthesizing critique for {len(content)} characters")
        
        # Perform all available analyses
        argument_analysis = analyze_argument_structure(content, url)
        consistency_analysis = assess_editorial_consistency(content, url)
        fallacy_analysis = detect_logical_fallacies(content, url)
        credibility_analysis = assess_source_credibility(content, url)
        
        # Synthesize overall critique score
        critique_score = _calculate_overall_critique_score(
            argument_analysis, consistency_analysis, fallacy_analysis, credibility_analysis
        )
        
        # Generate critique summary
        critique_summary = _generate_critique_summary(
            critique_score, argument_analysis, consistency_analysis, 
            fallacy_analysis, credibility_analysis
        )
        
        # Prepare result
        result = {
            "critique_score": critique_score,
            "critique_summary": critique_summary,
            "detailed_analysis": {
                "argument_structure": argument_analysis,
                "editorial_consistency": consistency_analysis,
                "logical_fallacies": fallacy_analysis,
                "source_credibility": credibility_analysis
            },
            "recommendations": _generate_critique_recommendations(
                critique_score, argument_analysis, consistency_analysis, 
                fallacy_analysis, credibility_analysis
            ),
            "analysis_metadata": {
                "content_length": len(content),
                "url": url,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_synthesis"
            }
        }
        
        # Collect prediction for training (confidence based on critique score)
        confidence = min(0.95, max(0.5, critique_score / 10.0))  # Scale to 0.5-0.95 range
        
        try:
            from training_system import collect_prediction
            collect_prediction(
                agent_name="critic",
                task_type="content_critique",
                input_text=content,
                prediction=result,
                confidence=confidence,
                source_url=url or ""
            )
            logger.debug(f"📊 Training data collected for critique synthesis (confidence: {confidence:.3f})")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")
        
        logger.info(f"✅ Critique synthesis complete: score {critique_score:.1f}/10")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error in critique synthesis: {e}")
        return {"error": str(e)}

def critique_neutrality(content: str, url: str = None) -> Dict[str, Any]:
    """
    Analyze content neutrality and bias indicators
    
    Args:
        content (str): Content to analyze for neutrality
        url (str, optional): Source URL for context
        
    Returns:
        Dict containing neutrality analysis
    """
    try:
        logger.info(f"⚖️ Analyzing neutrality for {len(content)} characters")
        
        # Analyze bias indicators (simplified - in production would use ML models)
        bias_indicators = _detect_bias_indicators(content)
        neutrality_score = _calculate_neutrality_score(content, bias_indicators)
        
        # Analyze language objectivity
        objectivity_analysis = _analyze_language_objectivity(content)
        
        # Analyze perspective balance
        perspective_balance = _analyze_perspective_balance(content)
        
        # Synthesize neutrality assessment
        assessment = {
            "neutrality_score": neutrality_score,
            "bias_indicators": bias_indicators,
            "objectivity_analysis": objectivity_analysis,
            "perspective_balance": perspective_balance,
            "overall_assessment": _generate_neutrality_assessment(neutrality_score, bias_indicators),
            "recommendations": _generate_neutrality_recommendations(neutrality_score, bias_indicators),
            "analysis_metadata": {
                "content_length": len(content),
                "url": url,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzer_version": "critic_v2_neutrality"
            }
        }
        
        # Collect prediction for training
        confidence = min(0.95, max(0.5, neutrality_score / 10.0))
        
        try:
            from training_system import collect_prediction
            collect_prediction(
                agent_name="critic",
                task_type="neutrality_analysis",
                input_text=content,
                prediction=assessment,
                confidence=confidence,
                source_url=url or ""
            )
            logger.debug(f"📊 Training data collected for neutrality analysis (confidence: {confidence:.3f})")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")
        
        logger.info(f"✅ Neutrality analysis complete: score {neutrality_score:.1f}/10")
        return assessment
        
    except Exception as e:
        logger.error(f"❌ Error in neutrality analysis: {e}")
        return {"error": str(e)}

# =============================================================================
# ESSENTIAL HELPER FUNCTIONS
# =============================================================================

def _extract_premises(text: str) -> list[dict[str, Any]]:
    """Extract premises from argument text."""
    premise_indicators = ['because', 'since', 'given that', 'as', 'due to']
    premises = []
    sentences = re.split(r'[.!?]+', text)

    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue
        for indicator in premise_indicators:
            if indicator in sentence.lower():
                premises.append({
                    "text": sentence,
                    "indicator": indicator,
                    "position": i,
                    "strength": 0.7
                })
                break
    return premises

def _extract_conclusions(text: str) -> list[dict[str, Any]]:
    """Extract conclusions from argument text."""
    conclusion_indicators = ['therefore', 'thus', 'hence', 'so', 'consequently']
    conclusions = []
    sentences = re.split(r'[.!?]+', text)

    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue
        for indicator in conclusion_indicators:
            if indicator in sentence.lower():
                conclusions.append({
                    "text": sentence,
                    "indicator": indicator,
                    "position": i,
                    "strength": 0.7
                })
                break
    return conclusions

def _analyze_logical_flow(text: str) -> dict[str, Any]:
    """Analyze logical flow and connectors."""
    connectors = ['however', 'but', 'furthermore', 'moreover', 'additionally']
    found_connectors = []

    for connector in connectors:
        if connector in text.lower():
            found_connectors.append({"connector": connector, "type": "transition"})

    return {
        "connectors": found_connectors,
        "flow_coherence": min(1.0, len(found_connectors) / 3.0)
    }

def _assess_argument_strength(text: str, premises: list[dict], conclusions: list[dict]) -> dict[str, Any]:
    """Assess overall argument strength."""
    if not premises and not conclusions:
        return {"strength_score": 0.0, "assessment": "No clear argumentative structure"}

    premise_count = len(premises)
    conclusion_count = len(conclusions)
    balance_score = 1.0 - abs(premise_count - conclusion_count) / max(premise_count + conclusion_count, 1)

    return {
        "strength_score": balance_score,
        "premise_quality": 0.7,
        "conclusion_quality": 0.7,
        "balance_score": balance_score,
        "assessment": "Moderate argumentative structure"
    }

def _calculate_argument_complexity(premises: list[dict], conclusions: list[dict]) -> float:
    """Calculate argument complexity score."""
    return min((len(premises) + len(conclusions)) / 2.0, 10.0)

def _calculate_coherence_score(text: str) -> float:
    """Calculate text coherence."""
    sentences = re.split(r'[.!?]+', text)
    valid_sentences = [s.strip() for s in sentences if s.strip()]

    if len(valid_sentences) < 2:
        return 0.5

    # Simple coherence based on sentence length consistency
    sentence_lengths = [len(s.split()) for s in valid_sentences]
    if len(sentence_lengths) > 1:
        avg_length = statistics.mean(sentence_lengths)
        variation = statistics.stdev(sentence_lengths) if len(sentence_lengths) > 1 else 0
        coherence = 1.0 - min(variation / avg_length, 1.0)
    else:
        coherence = 1.0

    return coherence

def _detect_contradictions(text: str) -> list[dict[str, Any]]:
    """Detect internal contradictions."""
    contradictions = []
    sentences = re.split(r'[.!?]+', text)

    # Simple contradiction detection
    for i, sentence1 in enumerate(sentences):
        for j, sentence2 in enumerate(sentences[i+1:], i+1):
            if 'not' in sentence1.lower() and any(word in sentence2.lower() for word in sentence1.lower().split() if word != 'not'):
                contradictions.append({
                    "sentence1": sentence1.strip(),
                    "sentence2": sentence2.strip(),
                    "confidence": 0.5
                })

    return contradictions[:3]  # Limit to top 3

def _detect_common_fallacies(text: str) -> list[dict[str, Any]]:
    """Detect common logical fallacies."""
    fallacies = []

    # Ad hominem detection
    if any(phrase in text.lower() for phrase in ['attacks', 'character assassination', 'personally']):
        fallacies.append({
            "fallacy": "ad_hominem",
            "confidence": 0.6,
            "description": "Personal attack rather than addressing argument"
        })

    # Appeal to authority
    if any(phrase in text.lower() for phrase in ['expert says', 'authority claims', 'because someone said']):
        fallacies.append({
            "fallacy": "appeal_to_authority",
            "confidence": 0.5,
            "description": "Inappropriate appeal to authority"
        })

    return fallacies

def _extract_citations(text: str) -> list[dict[str, Any]]:
    """Extract citations and references."""
    citations = []

    # Look for citation patterns
    patterns = [
        (r'according to ([A-Z][a-z]+ [A-Z][a-z]+)', 'person'),
        (r'([A-Z][a-z]+ [A-Z][a-z]+) said', 'person'),
        (r'study by ([A-Z][A-Za-z\s]+)', 'study')
    ]

    for pattern, citation_type in patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            citations.append({
                "text": match.group(1),
                "type": citation_type,
                "position": match.start()
            })

    return citations


def get_llama_model():
    """Compatibility shim for tests that expect get_llama_model to exist.

    Return a (model, tokenizer) tuple or (None, None). Tests typically
    monkeypatch this function during unit tests; a lightweight shim
    prevents AttributeError during collection.
    """
    return (None, None)

def _calculate_overall_critique_score(argument_analysis, consistency_analysis, 
                                   fallacy_analysis, credibility_analysis) -> float:
    """Calculate overall critique score from individual analyses"""
    try:
        # Extract scores from each analysis (0-1 scale, convert to 0-10)
        argument_score = argument_analysis.get("argument_strength", {}).get("strength_score", 0.5) * 10
        consistency_score = consistency_analysis.get("consistency_score", 0.5) * 10
        fallacy_score = (1.0 - fallacy_analysis.get("fallacy_count", 0) * 0.3) * 10  # Invert fallacy count
        credibility_score = credibility_analysis.get("credibility_score", 0.5) * 10
        
        # Weighted average (argument structure most important)
        weights = {
            "argument": 0.4,
            "consistency": 0.3, 
            "fallacy": 0.2,
            "credibility": 0.1
        }
        
        overall_score = (
            argument_score * weights["argument"] +
            consistency_score * weights["consistency"] +
            fallacy_score * weights["fallacy"] +
            credibility_score * weights["credibility"]
        )
        
        return max(0.0, min(10.0, overall_score))
        
    except Exception:
        return 5.0  # Neutral score on error

def _generate_critique_summary(critique_score, argument_analysis, consistency_analysis,
                              fallacy_analysis, credibility_analysis) -> str:
    """Generate human-readable critique summary"""
    try:
        score_level = "excellent" if critique_score >= 8.0 else \
                     "good" if critique_score >= 6.0 else \
                     "adequate" if critique_score >= 4.0 else \
                     "poor" if critique_score >= 2.0 else "very poor"
        
        summary_parts = [f"Overall quality assessment: {score_level} ({critique_score:.1f}/10)"]
        
        # Add key findings
        if argument_analysis.get("argument_strength", {}).get("strength_score", 0.5) < 0.6:
            summary_parts.append("Weak argumentative structure detected")
        
        if consistency_analysis.get("consistency_score", 0.5) < 0.6:
            contradictions = consistency_analysis.get("contradictions", [])
            summary_parts.append(f"Editorial inconsistencies found ({len(contradictions)} issues)")
        
        fallacy_count = fallacy_analysis.get("fallacy_count", 0)
        if fallacy_count > 0:
            summary_parts.append(f"Logical fallacies detected ({fallacy_count} instances)")
        
        if credibility_analysis.get("credibility_score", 0.5) < 0.6:
            summary_parts.append("Limited source credibility indicators")
        
        return ". ".join(summary_parts)
        
    except Exception:
        return f"Critique analysis completed with score {critique_score:.1f}/10"

def _generate_critique_recommendations(critique_score, argument_analysis, consistency_analysis,
                                      fallacy_analysis, credibility_analysis) -> List[str]:
    """Generate improvement recommendations based on analysis"""
    recommendations = []
    
    try:
        # Argument structure recommendations
        if argument_analysis.get("argument_strength", {}).get("strength_score", 0.5) < 0.6:
            recommendations.append("Strengthen argumentative structure with clearer premises and conclusions")
        
        # Consistency recommendations
        if consistency_analysis.get("consistency_score", 0.5) < 0.6:
            recommendations.append("Review and resolve editorial inconsistencies")
        
        # Fallacy recommendations
        fallacy_count = fallacy_analysis.get("fallacy_count", 0)
        if fallacy_count > 0:
            recommendations.append("Address logical fallacies and improve reasoning quality")
        
        # Credibility recommendations
        if credibility_analysis.get("credibility_score", 0.5) < 0.6:
            recommendations.append("Enhance source credibility with additional citations and references")
        
        # Overall quality recommendations
        if critique_score < 4.0:
            recommendations.append("Major revision recommended - content requires significant improvement")
        elif critique_score < 6.0:
            recommendations.append("Moderate improvements needed for publication readiness")
        elif critique_score < 8.0:
            recommendations.append("Minor polishing recommended for optimal quality")
        else:
            recommendations.append("Content meets high-quality standards")
        
        return recommendations[:5]  # Limit to top 5 recommendations
        
    except Exception:
        return ["Manual review recommended due to analysis error"]

def _detect_bias_indicators(content: str) -> List[Dict[str, Any]]:
    """Detect potential bias indicators in content"""
    bias_indicators = []
    content_lower = content.lower()
    
    # Political bias indicators
    political_terms = {
        "left": ["liberal", "progressive", "democrat", "left-wing"],
        "right": ["conservative", "republican", "right-wing", "traditional"],
        "neutral": ["bipartisan", "centrist", "moderate", "balanced"]
    }
    
    for bias_type, terms in political_terms.items():
        for term in terms:
            if term in content_lower:
                bias_indicators.append({
                    "type": "political",
                    "bias_direction": bias_type,
                    "indicator": term,
                    "context": _get_word_context(content, term),
                    "strength": 0.6
                })
    
    # Sensationalism indicators
    sensational_terms = ["shocking", "outrageous", "unbelievable", "scandal", "crisis", "disaster"]
    for term in sensational_terms:
        if term in content_lower:
            bias_indicators.append({
                "type": "sensationalism",
                "indicator": term,
                "context": _get_word_context(content, term),
                "strength": 0.4
            })
    
    # Loaded language indicators
    loaded_terms = ["obviously", "clearly", "undoubtedly", "of course", "everyone knows"]
    for term in loaded_terms:
        if term in content_lower:
            bias_indicators.append({
                "type": "loaded_language",
                "indicator": term,
                "context": _get_word_context(content, term),
                "strength": 0.5
            })
    
    return bias_indicators

def _calculate_neutrality_score(content: str, bias_indicators: List[Dict]) -> float:
    """Calculate overall neutrality score"""
    try:
        base_score = 8.0  # Start with high neutrality assumption
        
        # Reduce score based on bias indicators
        for indicator in bias_indicators:
            base_score -= indicator.get("strength", 0.5)
        
        # Reduce score for imbalanced perspective
        perspective_score = _analyze_perspective_balance(content).get("balance_score", 0.5)
        base_score = base_score * 0.7 + perspective_score * 10 * 0.3
        
        # Reduce score for lack of source attribution
        attribution_score = _assess_source_attribution(content)
        base_score = base_score * 0.8 + attribution_score * 10 * 0.2
        
        return max(0.0, min(10.0, base_score))
        
    except Exception:
        return 5.0

def _analyze_language_objectivity(content: str) -> Dict[str, Any]:
    """Analyze language objectivity indicators"""
    try:
        # Count objective vs subjective language
        objective_indicators = ["according to", "research shows", "data indicates", "study finds"]
        subjective_indicators = ["i believe", "in my opinion", "i think", "clearly", "obviously"]
        
        objective_count = sum(1 for ind in objective_indicators if ind in content.lower())
        subjective_count = sum(1 for ind in subjective_indicators if ind in content.lower())
        
        objectivity_ratio = objective_count / max(1, objective_count + subjective_count)
        
        return {
            "objective_indicators": objective_count,
            "subjective_indicators": subjective_count,
            "objectivity_ratio": objectivity_ratio,
            "objectivity_score": objectivity_ratio * 10
        }
        
    except Exception:
        return {"objectivity_score": 5.0}

def _analyze_perspective_balance(content: str) -> Dict[str, Any]:
    """Analyze balance of different perspectives"""
    try:
        # Simple heuristic: look for counter-arguments or alternative views
        balance_indicators = ["however", "on the other hand", "alternatively", "critics argue", "supporters say"]
        balance_count = sum(1 for ind in balance_indicators if ind in content.lower())
        
        # Assess quote balance
        quote_count = content.count('"')
        balance_score = min(1.0, (balance_count * 0.3 + quote_count * 0.1))
        
        return {
            "balance_indicators": balance_count,
            "quote_count": quote_count,
            "balance_score": balance_score
        }
        
    except Exception:
        return {"balance_score": 0.5}

def _assess_source_attribution(content: str) -> float:
    """Assess quality of source attribution"""
    try:
        attribution_indicators = ["according to", "cited by", "source:", "reference:"]
        attribution_count = sum(1 for ind in attribution_indicators if ind in content.lower())
        
        # Normalize to 0-1 scale
        return min(1.0, attribution_count / 3.0)
        
    except Exception:
        return 0.5

def _generate_neutrality_assessment(neutrality_score: float, bias_indicators: List[Dict]) -> str:
    """Generate neutrality assessment summary"""
    try:
        if neutrality_score >= 8.0:
            assessment = "Highly neutral and balanced content"
        elif neutrality_score >= 6.0:
            assessment = "Generally neutral with minor bias indicators"
        elif neutrality_score >= 4.0:
            assessment = "Moderate neutrality concerns requiring attention"
        else:
            assessment = "Significant neutrality issues detected"
        
        if bias_indicators:
            assessment += f" ({len(bias_indicators)} bias indicators found)"
        
        return assessment
        
    except Exception:
        return "Neutrality assessment completed"

def _generate_neutrality_recommendations(neutrality_score: float, bias_indicators: List[Dict]) -> List[str]:
    """Generate neutrality improvement recommendations"""
    recommendations = []
    
    try:
        if neutrality_score < 6.0:
            recommendations.append("Review content for potential bias and ensure balanced perspective")
        
        if any(ind["type"] == "political" for ind in bias_indicators):
            recommendations.append("Balance political perspectives and avoid partisan language")
        
        if any(ind["type"] == "sensationalism" for ind in bias_indicators):
            recommendations.append("Tone down sensational language for more objective reporting")
        
        if neutrality_score < 4.0:
            recommendations.append("Major revision needed - content shows significant bias")
        
        if not recommendations:
            recommendations.append("Content maintains good neutrality standards")
        
        return recommendations
        
    except Exception:
        return ["Manual neutrality review recommended"]

def _get_word_context(text: str, word: str, context_chars: int = 50) -> str:
    """Get context around a word in text"""
    try:
        word_lower = word.lower()
        text_lower = text.lower()
        start_idx = text_lower.find(word_lower)
        
        if start_idx == -1:
            return ""
        
        start = max(0, start_idx - context_chars)
        end = min(len(text), start_idx + len(word) + context_chars)
        
        context = text[start:end]
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."
            
        return context
        
    except Exception:
        return ""
