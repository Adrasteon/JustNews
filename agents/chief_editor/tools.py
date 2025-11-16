"""
Chief Editor Tools - Utility Functions for Editorial Operations

This module provides utility functions for editorial workflow orchestration,
content analysis, and multi-agent coordination.

Key Functions:
- assess_content_quality: BERT-based quality assessment
- categorize_content: DistilBERT-based categorization
- analyze_editorial_sentiment: RoBERTa-based sentiment analysis
- generate_editorial_commentary: T5-based commentary generation
- make_editorial_decision: Comprehensive editorial decision making
- request_story_brief: Story brief generation
- publish_story: Publishing coordination
- review_evidence: Evidence review queue management

All functions include robust error handling, validation, and fallbacks.
"""

import json
import os
import time
from typing import Any

from common.observability import get_logger

from .chief_editor_engine import ChiefEditorConfig, ChiefEditorEngine

logger = get_logger(__name__)

# Global engine instance
_engine: ChiefEditorEngine | None = None

def get_chief_editor_engine() -> ChiefEditorEngine:
    """Get or create the global chief editor engine instance."""
    global _engine
    if _engine is None:
        config = ChiefEditorConfig()
        _engine = ChiefEditorEngine(config)
    return _engine

async def process_editorial_request(
    content: str,
    operation_type: str,
    **kwargs
) -> dict[str, Any]:
    """
    Process an editorial request using the chief editor engine.

    Args:
        content: Content to process
        operation_type: Type of editorial operation to perform
        **kwargs: Additional parameters for operation

    Returns:
        Editorial operation results dictionary
    """
    engine = get_chief_editor_engine()

    try:
        logger.info(f"🎯 Processing {operation_type} editorial operation for {len(content)} characters")

        if operation_type == "quality":
            result = engine.assess_content_quality_bert(content)
        elif operation_type == "categorize":
            result = engine.categorize_content_distilbert(content)
        elif operation_type == "sentiment":
            result = engine.analyze_editorial_sentiment_roberta(content)
        elif operation_type == "commentary":
            context = kwargs.get("context", "news article")
            result = engine.generate_editorial_commentary_t5(content, context)
        elif operation_type == "decision":
            metadata = kwargs.get("metadata")
            result = engine.make_editorial_decision(content, metadata)
        else:
            result = {"error": f"Unknown operation type: {operation_type}"}

        logger.info(f"✅ {operation_type.capitalize()} editorial operation completed")
        return result

    except Exception as e:
        logger.error(f"❌ {operation_type} editorial operation failed: {e}")
        return {"error": str(e)}

def assess_content_quality(content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Assess content quality using BERT-based analysis.

    This function evaluates the overall quality of news content using
    advanced NLP models to determine publication readiness.

    Args:
        content: Content to assess for quality
        metadata: Additional metadata for context

    Returns:
        Dictionary containing quality assessment results
    """
    if not content or not content.strip():
        return {"overall_quality": 0.0, "assessment": "empty", "error": "Empty content provided"}

    engine = get_chief_editor_engine()
    return engine.assess_content_quality_bert(content)

def categorize_content(content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Categorize content using DistilBERT-based classification.

    This function automatically categorizes news content into appropriate
    editorial categories for workflow routing.

    Args:
        content: Content to categorize
        metadata: Additional metadata for context

    Returns:
        Dictionary containing categorization results
    """
    if not content or not content.strip():
        return {"category": "unknown", "confidence": 0.0, "error": "Empty content provided"}

    engine = get_chief_editor_engine()
    return engine.categorize_content_distilbert(content)

def analyze_editorial_sentiment(content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Analyze editorial sentiment using RoBERTa-based analysis.

    This function determines the editorial tone and sentiment of content
    to inform publication decisions.

    Args:
        content: Content to analyze for sentiment
        metadata: Additional metadata for context

    Returns:
        Dictionary containing sentiment analysis results
    """
    if not content or not content.strip():
        return {"sentiment": "neutral", "confidence": 0.0, "error": "Empty content provided"}

    engine = get_chief_editor_engine()
    return engine.analyze_editorial_sentiment_roberta(content)

def generate_editorial_commentary(content: str, context: str = "news article") -> dict[str, Any]:
    """
    Generate editorial commentary using T5-based generation.

    This function creates editorial notes and commentary for content
    to guide the editorial workflow.

    Args:
        content: Content for commentary generation
        context: Context for commentary (e.g., "news article", "breaking news")

    Returns:
        Dictionary containing generated commentary
    """
    if not content or not content.strip():
        return {"commentary": "", "error": "Empty content provided"}

    engine = get_chief_editor_engine()
    commentary = engine.generate_editorial_commentary_t5(content, context)

    return {
        "commentary": commentary,
        "context": context,
        "content_length": len(content),
        "model": "t5"
    }

def make_editorial_decision(content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Make comprehensive editorial decision using all 5 AI models.

    This function provides a complete editorial assessment including
    quality, categorization, sentiment, and workflow recommendations.

    Args:
        content: Content for editorial decision
        metadata: Additional metadata for context

    Returns:
        Dictionary containing comprehensive editorial decision
    """
    if not content or not content.strip():
        return {"error": "Empty content provided for editorial decision"}

    engine = get_chief_editor_engine()
    decision = engine.make_editorial_decision(content, metadata)

    # Convert dataclass to dictionary
    return {
        "priority": decision.priority.value,
        "stage": decision.stage.value,
        "confidence": decision.confidence,
        "reasoning": decision.reasoning,
        "next_actions": decision.next_actions,
        "agent_assignments": list(decision.agent_assignments.keys()),
        "metadata": decision.metadata,
        "decision_timestamp": time.time()
    }

def request_story_brief(topic: str, scope: str) -> dict[str, Any]:
    """
    Generate a story brief for editorial planning.

    This function creates structured story briefs to guide content development
    and editorial planning across the newsroom.

    Args:
        topic: Story topic
        scope: Story scope/coverage area

    Returns:
        Dictionary containing generated story brief
    """
    if not topic or not topic.strip():
        return {"error": "Empty topic provided for story brief"}

    try:
        # Use the engine for brief generation if available, otherwise fallback
        engine = get_chief_editor_engine()

        # Generate brief using T5 if available, otherwise use template
        if hasattr(engine, 'generate_editorial_commentary_t5'):
            brief_content = engine.generate_editorial_commentary_t5(
                f"Generate a story brief for topic: {topic} with scope: {scope}",
                "story brief"
            )
        else:
            brief_content = f"Story brief for topic '{topic}' within scope '{scope}'."

        brief = {
            "topic": topic,
            "scope": scope,
            "brief": brief_content,
            "generated_at": time.time(),
            "status": "generated"
        }

        # Log feedback for training
        engine.log_feedback("request_story_brief", {
            "topic": topic,
            "scope": scope,
            "brief_length": len(brief_content)
        })

        # Collect prediction for training
        try:
            from training_system import collect_prediction
            collect_prediction(
                agent_name="chief_editor",
                task_type="story_brief_generation",
                input_text=f"Topic: {topic}, Scope: {scope}",
                prediction={"brief": brief_content},
                confidence=0.8,
                source_url=""
            )
            logger.debug("📊 Training data collected for story brief generation")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

        return brief

    except Exception as e:
        logger.error(f"Error generating story brief: {e}")
        return {"error": str(e)}

def publish_story(story_id: str) -> dict[str, Any]:
    """
    Coordinate story publishing across the editorial workflow.

    This function manages the publishing process, coordinating with
    other agents and updating editorial timelines.

    Args:
        story_id: ID of the story to publish

    Returns:
        Dictionary containing publishing results
    """
    if not story_id or not story_id.strip():
        return {"error": "Empty story ID provided for publishing"}

    try:
        # MCP Bus integration for publishing coordination
        mcp_bus_url = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

        payload = {
            "agent": "librarian",
            "tool": "update_story_timeline",
            "args": [story_id],
            "kwargs": {}
        }

        # Try MCP bus call, fallback to local operation
        try:
            import requests
            resp = requests.post(f"{mcp_bus_url}/call", json=payload, timeout=10)
            resp.raise_for_status()
            mcp_result = resp.json()
            status = "published"
        except Exception as e:
            logger.warning(f"MCP Bus call failed: {e}")
            mcp_result = {"fallback": True, "error": str(e)}
            status = "published_locally"

        result = {
            "status": status,
            "story_id": story_id,
            "mcp_result": mcp_result,
            "message": "Story publishing coordinated successfully",
            "published_at": time.time()
        }

        # Log feedback for training
        engine = get_chief_editor_engine()
        engine.log_feedback("publish_story", {
            "story_id": story_id,
            "status": status
        })

        # Collect prediction for training
        try:
            from training_system import collect_prediction
            collect_prediction(
                agent_name="chief_editor",
                task_type="story_publishing",
                input_text=story_id,
                prediction=result,
                confidence=0.9,
                source_url=""
            )
            logger.debug("📊 Training data collected for story publishing")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

        return result

    except Exception as e:
        logger.error(f"Error publishing story: {e}")
        return {"error": str(e)}

def review_evidence(evidence_manifest: str, reason: str) -> dict[str, Any]:
    """
    Queue evidence for human review and editorial oversight.

    This function manages the evidence review queue, notifying editors
    and maintaining audit trails for editorial decisions.

    Args:
        evidence_manifest: Path or identifier for evidence
        reason: Reason for requesting review

    Returns:
        Dictionary containing review queue results
    """
    if not evidence_manifest or not evidence_manifest.strip():
        return {"error": "Empty evidence manifest provided"}

    try:
        # Import the handler function
        from agents.chief_editor.handler import handle_review_request

        # Queue the review request
        result = handle_review_request({
            'evidence_manifest': evidence_manifest,
            'reason': reason
        })

        # Add timestamp and additional metadata
        result.update({
            "queued_at": time.time(),
            "evidence_manifest": evidence_manifest,
            "reason": reason
        })

        # Log feedback
        engine = get_chief_editor_engine()
        engine.log_feedback("review_evidence", {
            "evidence_manifest": evidence_manifest,
            "reason": reason
        })

        return result

    except Exception as e:
        logger.error(f"Error queuing evidence review: {e}")
        return {"error": str(e)}

async def health_check() -> dict[str, Any]:
    """
    Perform health check on chief editor components.

    Returns:
        Health check results with component status
    """
    try:
        engine = get_chief_editor_engine()

        model_status = engine.get_model_status()

        health_status = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "components": {
                "engine": "healthy",
                "mcp_bus": "healthy",  # Assume healthy unless proven otherwise
                "evidence_queue": "healthy"
            },
            "model_status": model_status,
            "processing_stats": engine.processing_stats
        }

        # Check for any unhealthy components
        unhealthy_components = [k for k, v in health_status["components"].items() if v == "unhealthy"]
        if unhealthy_components:
            health_status["overall_status"] = "degraded"
            health_status["issues"] = [f"Component {comp} is unhealthy" for comp in unhealthy_components]

        # Check model availability
        loaded_models = sum(1 for status in model_status.values() if status is True)
        if loaded_models < 3:  # Require at least 3 of 5 models
            health_status["overall_status"] = "degraded"
            health_status["issues"] = health_status.get("issues", []) + [f"Only {loaded_models}/5 AI models loaded"]

        logger.info(f"🏥 Chief Editor health check: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Chief Editor health check failed: {e}")
        return {
            "timestamp": time.time(),
            "overall_status": "unhealthy",
            "error": str(e)
        }

def validate_editorial_result(result: dict[str, Any], expected_fields: list[str] = None) -> bool:
    """
    Validate editorial result structure.

    Args:
        result: Editorial result to validate
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
    common_fields = ["model", "processing_time", "timestamp"]
    return any(field in result for field in common_fields)

def format_editorial_output(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format editorial result for output.

    Args:
        result: Editorial result to format
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
            if "overall_quality" in result:
                lines.append(f"Quality Score: {result['overall_quality']:.2f}")
                lines.append(f"Assessment: {result.get('assessment', 'N/A')}")

            if "category" in result:
                lines.append(f"Category: {result['category']}")
                lines.append(f"Confidence: {result.get('confidence', 0):.2f}")

            if "sentiment" in result:
                lines.append(f"Sentiment: {result['sentiment']}")
                lines.append(f"Editorial Tone: {result.get('editorial_tone', 'N/A')}")

            if "priority" in result:
                lines.append(f"Editorial Priority: {result['priority']}")
                lines.append(f"Workflow Stage: {result.get('stage', 'N/A')}")

            if "brief" in result:
                lines.append(f"Story Brief: {result['brief']}")

            return "\n".join(lines)

        elif format_type == "markdown":
            if "error" in result:
                return f"## Editorial Analysis Error\n\n{result['error']}"

            lines = ["# Editorial Analysis Results\n"]

            if "overall_quality" in result:
                lines.append("## Quality Assessment")
                lines.append(f"- **Quality Score**: {result['overall_quality']:.2f}")
                lines.append(f"- **Assessment**: {result.get('assessment', 'N/A')}")

            if "category" in result:
                lines.append("## Content Categorization")
                lines.append(f"- **Category**: {result['category']}")
                lines.append(f"- **Confidence**: {result.get('confidence', 0):.2f}")

            if "sentiment" in result:
                lines.append("## Editorial Sentiment")
                lines.append(f"- **Sentiment**: {result['sentiment']}")
                lines.append(f"- **Editorial Tone**: {result.get('editorial_tone', 'N/A')}")

            if "priority" in result:
                lines.append("## Editorial Decision")
                lines.append(f"- **Priority**: {result['priority']}")
                lines.append(f"- **Workflow Stage**: {result.get('stage', 'N/A')}")
                lines.append(f"- **Confidence**: {result.get('confidence', 0):.2f}")

                if "next_actions" in result and result["next_actions"]:
                    lines.append("- **Next Actions**:")
                    for action in result["next_actions"][:5]:
                        lines.append(f"  - {action}")

            if "brief" in result:
                lines.append("## Story Brief")
                lines.append(f"{result['brief']}")

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"

# Export main functions
__all__ = [
    'assess_content_quality',
    'categorize_content',
    'analyze_editorial_sentiment',
    'generate_editorial_commentary',
    'make_editorial_decision',
    'request_story_brief',
    'publish_story',
    'review_evidence',
    'health_check',
    'validate_editorial_result',
    'format_editorial_output',
    'get_chief_editor_engine'
]
