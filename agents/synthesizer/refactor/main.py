"""
Synthesizer Agent - Simplified FastAPI Application

This module provides a simplified synthesizer agent with GPU-accelerated
content synthesis capabilities using a 4-model architecture (BERTopic,
BART, FLAN-T5, SentenceTransformers).

Key Features:
- Article clustering and synthesis
- GPU acceleration with CPU fallbacks
- MCP bus integration
- Comprehensive error handling
- Performance monitoring

Endpoints:
- POST /cluster_articles: Cluster articles into themes
- POST /neutralize_text: Remove bias from text
- POST /aggregate_cluster: Aggregate cluster into summary
- POST /synthesize_news_articles_gpu: GPU-accelerated synthesis
- GET /health: Health check
- GET /stats: Performance statistics
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from common.observability import get_logger
from common.metrics import JustNewsMetrics

# Import refactored components
from .synthesizer_engine import SynthesizerEngine
from .tools import (
    cluster_articles_tool,
    neutralize_text_tool,
    aggregate_cluster_tool,
    synthesize_gpu_tool,
    health_check,
    get_stats
)

logger = get_logger(__name__)

# Environment variables
SYNTHESIZER_AGENT_PORT: int = int(os.environ.get("SYNTHESIZER_AGENT_PORT", 8005))
MCP_BUS_URL: str = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Global engine instance
synthesizer_engine: Optional[SynthesizerEngine] = None

class MCPBusClient:
    """Lightweight client for registering the agent with the central MCP Bus."""

    def __init__(self, base_url: str = MCP_BUS_URL) -> None:
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: List[str]) -> None:
        """Register an agent with the MCP bus."""
        import requests

        registration_data = {
            "name": agent_name,
            "address": agent_address,
            "tools": tools
        }
        try:
            response = requests.post(
                f"{self.base_url}/register", json=registration_data, timeout=(2, 5)
            )
            response.raise_for_status()
            logger.info("Successfully registered %s with MCP Bus.", agent_name)
        except Exception:
            logger.warning("MCP Bus unavailable; running in standalone mode.")
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown context manager for the FastAPI app."""
    global synthesizer_engine

    logger.info("🚀 Synthesizer agent is starting up.")

    # Initialize synthesizer engine
    try:
        synthesizer_engine = SynthesizerEngine()
        logger.info("✅ Synthesizer engine initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize synthesizer engine: {e}")
        synthesizer_engine = None

    # Register with MCP bus
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="synthesizer",
            agent_address=f"http://localhost:{SYNTHESIZER_AGENT_PORT}",
            tools=[
                "cluster_articles",
                "neutralize_text",
                "aggregate_cluster",
                "synthesize_news_articles_gpu",
                "get_synthesizer_performance",
            ],
        )
        logger.info("✅ Registered tools with MCP Bus.")
    except Exception:
        logger.warning("⚠️ MCP Bus unavailable; running in standalone mode.")

    yield

    # Cleanup on shutdown
    if synthesizer_engine:
        try:
            synthesizer_engine.cleanup()
            logger.info("🧹 Synthesizer engine cleanup completed")
        except Exception as e:
            logger.warning(f"⚠️ Engine cleanup warning: {e}")

    logger.info("🛑 Synthesizer agent is shutting down.")


app = FastAPI(
    title="Synthesizer Agent",
    description="GPU-accelerated news article synthesis and clustering",
    version="3.0.0",
    lifespan=lifespan
)

# Initialize metrics
metrics = JustNewsMetrics("synthesizer")
app.middleware("http")(metrics.request_middleware)

# Register common endpoints
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("Shutdown endpoint not registered")

try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("Reload endpoint not registered")


class ToolCall(BaseModel):
    """Standard MCP tool call format."""
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}


class SynthesisRequest(BaseModel):
    """Request model for synthesis operations."""
    articles: List[Dict[str, Any]]
    max_clusters: Optional[int] = 5
    context: Optional[str] = "news analysis"


@app.get("/health")
def health() -> Dict[str, str]:
    """Liveness probe."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    return {"status": "ok", "engine": "ready"}


@app.get("/ready")
def ready_endpoint() -> Dict[str, bool]:
    """Readiness probe."""
    return {"ready": synthesizer_engine is not None}


@app.get("/metrics")
def get_metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=metrics.get_metrics(), media_type="text/plain")


@app.post("/log_feedback")
def log_feedback(call: ToolCall) -> Dict[str, Any]:
    """Log feedback sent from other agents or tests."""
    try:
        feedback_data = {
            "timestamp": datetime.now().isoformat(),
            "feedback": call.kwargs.get("feedback"),
        }
        logger.info(f"📝 Logging feedback: {feedback_data}")
        return feedback_data
    except Exception as e:
        logger.exception("❌ Failed to log feedback")
        raise HTTPException(status_code=500, detail="Failed to log feedback")


@app.post("/cluster_articles")
def cluster_articles_endpoint(call: ToolCall) -> Any:
    """Cluster a list of articles into groups."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        # Extract parameters
        article_texts = call.args[0] if call.args else call.kwargs.get("article_texts", [])
        n_clusters = call.kwargs.get("n_clusters", 2)

        if not article_texts:
            raise HTTPException(status_code=400, detail="No articles provided")

        logger.info(f"🎯 Clustering {len(article_texts)} articles into {n_clusters} clusters")

        result = await cluster_articles_tool(synthesizer_engine, article_texts, n_clusters)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Cluster articles failed")
        raise HTTPException(status_code=500, detail=f"Clustering failed: {str(e)}")


@app.post("/neutralize_text")
def neutralize_text_endpoint(call: ToolCall) -> Any:
    """Neutralize text for bias and aggressive language."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        text = call.args[0] if call.args else call.kwargs.get("text", "")

        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="No text provided")

        logger.info(f"⚖️ Neutralizing text ({len(text)} chars)")

        result = await neutralize_text_tool(synthesizer_engine, text)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Neutralize text failed")
        raise HTTPException(status_code=500, detail=f"Neutralization failed: {str(e)}")


@app.post("/aggregate_cluster")
def aggregate_cluster_endpoint(call: ToolCall) -> Any:
    """Aggregate a cluster of articles into a synthesis."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        article_texts = call.args[0] if call.args else call.kwargs.get("article_texts", [])

        if not article_texts:
            raise HTTPException(status_code=400, detail="No articles provided")

        logger.info(f"📝 Aggregating {len(article_texts)} articles")

        result = await aggregate_cluster_tool(synthesizer_engine, article_texts)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Aggregate cluster failed")
        raise HTTPException(status_code=500, detail=f"Aggregation failed: {str(e)}")


@app.post("/synthesize_news_articles_gpu")
def synthesize_news_articles_gpu_endpoint(request: SynthesisRequest) -> Dict[str, Any]:
    """GPU-accelerated news article synthesis endpoint."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        if not request.articles:
            raise HTTPException(status_code=400, detail="No articles provided")

        logger.info(f"🚀 GPU synthesis: {len(request.articles)} articles, max_clusters={request.max_clusters}")

        result = await synthesize_gpu_tool(
            synthesizer_engine,
            request.articles,
            request.max_clusters,
            request.context
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ GPU synthesis failed")
        raise HTTPException(status_code=500, detail=f"GPU synthesis failed: {str(e)}")


@app.post("/get_synthesizer_performance")
def get_synthesizer_performance_endpoint(call: ToolCall) -> Dict[str, Any]:
    """Get synthesizer performance statistics."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        logger.info("📊 Retrieving synthesizer performance stats")
        result = await get_stats(synthesizer_engine)
        return result

    except Exception as e:
        logger.exception("❌ Performance stats failed")
        raise HTTPException(status_code=500, detail=f"Performance stats failed: {str(e)}")


# Health and stats endpoints
@app.get("/stats")
def get_stats_endpoint() -> Dict[str, Any]:
    """Get comprehensive synthesizer statistics."""
    if synthesizer_engine is None:
        return {"error": "Engine not initialized"}

    try:
        return health_check(synthesizer_engine)
    except Exception as e:
        logger.exception("❌ Stats endpoint failed")
        return {"error": str(e)}


# Compatibility aliases
@app.post("/synthesize_content")
def synthesize_content_alias(request: SynthesisRequest) -> Any:
    """Alias for compatibility with existing E2E tests."""
    return synthesize_news_articles_gpu_endpoint(request)


if __name__ == "__main__":
    import uvicorn

    host: str = os.environ.get("SYNTHESIZER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("SYNTHESIZER_PORT", SYNTHESIZER_AGENT_PORT))

    logger.info("🎯 Starting Synthesizer Agent on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)