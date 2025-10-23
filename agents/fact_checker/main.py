"""
Fact Checker Agent - Refactored Main Application

This module provides the main FastAPI application for the fact checker agent,
implementing comprehensive fact verification and source credibility assessment.

Key Features:
- MCP Bus integration for inter-agent communication
- Comprehensive fact-checking endpoints
- GPU-accelerated processing with CPU fallbacks
- Robust error handling and validation
- Performance monitoring and metrics
- Health checks and service discovery

Endpoints:
- /verify_facts: Primary fact verification endpoint
- /validate_sources: Source credibility assessment
- /validate_is_news_gpu: GPU-accelerated news validation
- /verify_claims_gpu: GPU-accelerated claim verification
- /comprehensive_fact_check: Full article fact-checking
- /health: Health check endpoint
- /ready: Readiness check endpoint
- /metrics: Prometheus metrics endpoint

All endpoints support both MCP Bus format and direct API calls.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from common.observability import get_logger

# Import metrics library
from common.metrics import JustNewsMetrics

# Configure logging
logger = get_logger(__name__)

ready = False

# Environment variables
FACT_CHECKER_AGENT_PORT = int(os.environ.get("FACT_CHECKER_AGENT_PORT", 8003))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

class MCPBusClient:
    """MCP Bus client for inter-agent communication."""

    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, tools: list):
        """Register agent with MCP Bus."""
        registration_data = {
            "name": agent_name,
            "address": f"http://localhost:{FACT_CHECKER_AGENT_PORT}",
            "tools": tools
        }
        try:
            response = requests.post(f"{self.base_url}/register", json=registration_data, timeout=(2, 5))
            response.raise_for_status()
            logger.info(f"Successfully registered {agent_name} with MCP Bus.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register {agent_name} with MCP Bus: {e}")
            raise

# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    logger.info("Fact Checker agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="fact_checker",
            tools=[
                "verify_facts",
                "validate_sources",
                "validate_is_news_gpu",
                "verify_claims_gpu",
                "comprehensive_fact_check",
                "extract_claims",
                "assess_credibility"
            ]
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield
    logger.info("Fact Checker agent is shutting down.")

# Initialize FastAPI with the lifespan context manager
app = FastAPI(
    title="Fact Checker Agent",
    description="AI-powered fact verification and source credibility assessment",
    version="2.0.0",
    lifespan=lifespan
)

# Initialize metrics
metrics = JustNewsMetrics("fact_checker")

# Register shutdown endpoint if available
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for fact_checker")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for fact_checker")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)

# Pydantic models for request/response validation
class ToolCall(BaseModel):
    """Standard MCP tool call format."""
    args: List[Any]
    kwargs: Dict[str, Any]

class FactCheckRequest(BaseModel):
    """Request model for fact checking operations."""
    content: str
    source_url: Optional[str] = None
    context: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class VerificationResult(BaseModel):
    """Response model for verification results."""
    verification_score: float
    classification: str
    confidence: float
    details: Dict[str, Any]
    processing_time: float
    timestamp: str

@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/ready")
def ready_endpoint():
    """Readiness check endpoint."""
    return {"ready": ready}

@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    return Response(metrics.get_metrics(), media_type="text/plain")

@app.post("/verify_facts")
async def verify_facts(call: ToolCall) -> Dict[str, Any]:
    """
    Primary fact verification endpoint.

    Verifies factual claims using AI models and evidence assessment.
    """
    try:
        from .tools import verify_facts

        logger.info(f"Calling verify_facts with args: {call.args} and kwargs: {call.kwargs}")

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")
        source_url = call.kwargs.get("source_url", "")
        context = call.kwargs.get("context", "")

        if not content:
            raise HTTPException(status_code=400, detail="Content parameter is required")

        result = await verify_facts(content, source_url, context)

        logger.info(f"Fact verification completed with score: {result.get('verification_score', 0.0)}")
        return result

    except Exception as e:
        logger.error(f"An error occurred in verify_facts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/validate_sources")
async def validate_sources(call: ToolCall) -> Dict[str, Any]:
    """
    Source credibility assessment endpoint.

    Evaluates the reliability and credibility of information sources.
    """
    try:
        from .tools import validate_sources

        logger.info(f"Calling validate_sources with args: {call.args} and kwargs: {call.kwargs}")

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")
        source_url = call.kwargs.get("source_url", "")
        domain = call.kwargs.get("domain", "")

        if not content and not source_url:
            raise HTTPException(status_code=400, detail="Either content or source_url parameter is required")

        result = await validate_sources(content, source_url, domain)

        logger.info(f"Source validation completed with credibility score: {result.get('credibility_score', 0.0)}")
        return result

    except Exception as e:
        logger.error(f"An error occurred in validate_sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/validate_is_news_gpu")
async def validate_is_news_gpu(call: ToolCall) -> Dict[str, Any]:
    """
    GPU-accelerated news content validation endpoint.

    Determines if provided content qualifies as legitimate news reporting.
    """
    try:
        from .tools import validate_is_news_gpu

        logger.info(f"Calling GPU validate_is_news with args: {call.args} and kwargs: {call.kwargs}")

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")

        if not content:
            raise HTTPException(status_code=400, detail="Content parameter is required")

        result = await validate_is_news_gpu(content)

        logger.info(f"GPU news validation completed: {result.get('is_news', False)}")
        return result

    except Exception as e:
        logger.error(f"An error occurred in GPU validate_is_news: {e}")
        # Fallback to CPU implementation
        try:
            from .tools import validate_is_news_cpu
            content = call.kwargs.get("content") or (call.args[0] if call.args else "")
            result = await validate_is_news_cpu(content)
            logger.info("Fallback to CPU news validation successful")
            return result
        except Exception as fallback_error:
            logger.error(f"Fallback CPU validation also failed: {fallback_error}")
            raise HTTPException(status_code=500, detail=f"GPU and CPU validation failed: {str(e)}")

@app.post("/verify_claims_gpu")
async def verify_claims_gpu(call: ToolCall) -> Dict[str, Any]:
    """
    GPU-accelerated claim verification endpoint.

    Verifies multiple claims against available evidence and sources.
    """
    try:
        from .tools import verify_claims_gpu

        logger.info(f"Calling GPU verify_claims with args: {call.args} and kwargs: {call.kwargs}")

        # Extract parameters
        claims = call.kwargs.get("claims") or (call.args[0] if call.args else [])
        sources = call.kwargs.get("sources") or (call.args[1] if len(call.args) > 1 else [])

        if not claims:
            raise HTTPException(status_code=400, detail="Claims parameter is required")

        result = await verify_claims_gpu(claims, sources)

        logger.info(f"GPU claims verification completed for {len(claims)} claims")
        return result

    except Exception as e:
        logger.error(f"An error occurred in GPU verify_claims: {e}")
        # Fallback to CPU implementation
        try:
            from .tools import verify_claims_cpu
            claims = call.kwargs.get("claims") or (call.args[0] if call.args else [])
            sources = call.kwargs.get("sources") or (call.args[1] if len(call.args) > 1 else [])
            result = await verify_claims_cpu(claims, sources)
            logger.info("Fallback to CPU claims verification successful")
            return result
        except Exception as fallback_error:
            logger.error(f"Fallback CPU verification also failed: {fallback_error}")
            raise HTTPException(status_code=500, detail=f"GPU and CPU verification failed: {str(e)}")

@app.post("/comprehensive_fact_check")
async def comprehensive_fact_check_endpoint(request: FactCheckRequest) -> Dict[str, Any]:
    """
    Comprehensive fact-checking endpoint for full articles.

    Performs complete fact verification analysis including claim extraction,
    evidence assessment, and source credibility evaluation.
    """
    try:
        from .tools import comprehensive_fact_check

        logger.info(f"Starting comprehensive fact check for content length: {len(request.content)}")

        result = await comprehensive_fact_check(
            request.content,
            request.source_url,
            request.context,
            request.metadata
        )

        logger.info(f"Comprehensive fact check completed with overall score: {result.get('overall_score', 0.0)}")
        return result

    except Exception as e:
        logger.error(f"An error occurred in comprehensive_fact_check: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract_claims")
async def extract_claims(call: ToolCall) -> Dict[str, Any]:
    """
    Claim extraction endpoint.

    Extracts verifiable claims from text content using NLP techniques.
    """
    try:
        from .tools import extract_claims

        logger.info(f"Calling extract_claims with args: {call.args} and kwargs: {call.kwargs}")

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")

        if not content:
            raise HTTPException(status_code=400, detail="Content parameter is required")

        result = await extract_claims(content)

        logger.info(f"Claim extraction completed: {result.get('claim_count', 0)} claims found")
        return result

    except Exception as e:
        logger.error(f"An error occurred in extract_claims: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/assess_credibility")
async def assess_credibility(call: ToolCall) -> Dict[str, Any]:
    """
    Source credibility assessment endpoint.

    Evaluates the credibility and reliability of information sources.
    """
    try:
        from .tools import assess_credibility

        logger.info(f"Calling assess_credibility with args: {call.args} and kwargs: {call.kwargs}")

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")
        domain = call.kwargs.get("domain", "")
        source_url = call.kwargs.get("source_url", "")

        if not content and not domain and not source_url:
            raise HTTPException(status_code=400, detail="At least one of content, domain, or source_url is required")

        result = await assess_credibility(content, domain, source_url)

        logger.info(f"Credibility assessment completed with score: {result.get('credibility_score', 0.0)}")
        return result

    except Exception as e:
        logger.error(f"An error occurred in assess_credibility: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/detect_contradictions")
async def detect_contradictions(call: ToolCall) -> Dict[str, Any]:
    """
    Contradiction detection endpoint.

    Identifies logical contradictions and inconsistencies in text passages.
    """
    try:
        from .tools import detect_contradictions

        logger.info(f"Calling detect_contradictions with args: {call.args} and kwargs: {call.kwargs}")

        # Extract parameters
        text_passages = call.kwargs.get("text_passages") or (call.args[0] if call.args else [])

        if not text_passages or len(text_passages) < 2:
            raise HTTPException(status_code=400, detail="At least 2 text passages are required for contradiction detection")

        result = await detect_contradictions(text_passages)

        logger.info(f"Contradiction detection completed: {result.get('contradictions_found', 0)} contradictions found")
        return result

    except Exception as e:
        logger.error(f"An error occurred in detect_contradictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/performance/stats")
def get_performance_stats():
    """Get GPU acceleration performance statistics."""
    try:
        from .tools import get_performance_stats
        return get_performance_stats()
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return {"error": str(e), "gpu_available": False}

@app.get("/model/status")
def get_model_status():
    """Get status of all fact-checking models."""
    try:
        from .tools import get_model_status
        return get_model_status()
    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        return {"error": str(e), "models_loaded": False}

@app.post("/log_feedback")
def log_feedback(call: ToolCall) -> Dict[str, Any]:
    """Log user feedback for model improvement."""
    try:
        from .tools import log_feedback

        feedback_data = {
            "timestamp": datetime.now().isoformat(),
            "operation": call.kwargs.get("operation", "unknown"),
            "feedback": call.kwargs.get("feedback"),
            "rating": call.kwargs.get("rating"),
            "comments": call.kwargs.get("comments")
        }

        result = log_feedback(feedback_data)

        logger.info(f"Feedback logged: {feedback_data.get('operation', 'unknown')}")
        return result

    except Exception as e:
        logger.error(f"An error occurred while logging feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/correct_verification")
def correct_verification(call: ToolCall) -> Dict[str, Any]:
    """Submit user correction for fact verification."""
    try:
        from .tools import correct_verification

        correction_data = {
            "claim": call.kwargs.get("claim"),
            "context": call.kwargs.get("context"),
            "incorrect_classification": call.kwargs.get("incorrect_classification"),
            "correct_classification": call.kwargs.get("correct_classification"),
            "priority": call.kwargs.get("priority", 2)
        }

        result = correct_verification(**correction_data)

        logger.info(f"Verification correction submitted: {correction_data.get('claim', '')[:50]}...")
        return result

    except Exception as e:
        logger.error(f"An error occurred while submitting verification correction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/correct_credibility")
def correct_credibility(call: ToolCall) -> Dict[str, Any]:
    """Submit user correction for credibility assessment."""
    try:
        from .tools import correct_credibility

        correction_data = {
            "source_text": call.kwargs.get("source_text"),
            "domain": call.kwargs.get("domain"),
            "incorrect_reliability": call.kwargs.get("incorrect_reliability"),
            "correct_reliability": call.kwargs.get("correct_reliability"),
            "priority": call.kwargs.get("priority", 2)
        }

        result = correct_credibility(**correction_data)

        logger.info(f"Credibility correction submitted for domain: {correction_data.get('domain', 'unknown')}")
        return result

    except Exception as e:
        logger.error(f"An error occurred while submitting credibility correction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/training/status")
def get_training_status():
    """Get online training status for fact checker models."""
    try:
        from .tools import get_training_status
        return get_training_status()
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        return {"error": str(e), "online_training_enabled": False}

@app.post("/force_update")
def force_model_update() -> Dict[str, Any]:
    """Force immediate model update (admin function)."""
    try:
        from .tools import force_model_update
        result = force_model_update()
        logger.info(f"Model update triggered: {result.get('update_triggered', False)}")
        return result
    except Exception as e:
        logger.error(f"An error occurred while forcing model update: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Legacy endpoint compatibility
@app.post("/validate_is_news")
def validate_is_news_legacy(call: ToolCall) -> Dict[str, Any]:
    """Legacy endpoint for backward compatibility."""
    return validate_is_news_gpu(call)

@app.post("/verify_claims")
def verify_claims_legacy(call: ToolCall) -> Dict[str, Any]:
    """Legacy endpoint for backward compatibility."""
    return verify_claims_gpu(call)

@app.post("/validate_claims")
def validate_claims_legacy(request: dict) -> Dict[str, Any]:
    """Legacy endpoint for backward compatibility."""
    try:
        # Handle MCP Bus format
        if "args" in request and len(request["args"]) > 0:
            content = request["args"][0]
        elif "kwargs" in request and "content" in request["kwargs"]:
            content = request["kwargs"]["content"]
        else:
            raise ValueError("Missing 'content' in request")

        # Perform basic validation
        validation_score = 0.75  # Placeholder score
        return {"validation_score": validation_score, "legacy_endpoint": True}
    except ValueError as ve:
        logger.warning(f"Validation error in legacy validate_claims: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"An error occurred in legacy validate_claims: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("FACT_CHECKER_HOST", "0.0.0.0")
    port = int(os.environ.get("FACT_CHECKER_PORT", 8003))

    logger.info(f"Starting Fact Checker Agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port)