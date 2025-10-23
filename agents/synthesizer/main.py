"""
Main file for the Synthesizer Agent.
"""
# main.py for Synthesizer Agent
from typing import List
from typing import Any
from typing import Dict
import os
from contextlib import asynccontextmanager
from datetime import datetime

import requests
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from common.observability import get_logger
from common.metrics import JustNewsMetrics

# Configure centralized logging
logger = get_logger(__name__)

ready: bool = False

# Environment variables
SYNTHESIZER_AGENT_PORT: int = int(os.environ.get("SYNTHESIZER_AGENT_PORT", 8005))
MCP_BUS_URL: str = os.environ.get("MCP_BUS_URL", "http://localhost:8000")


class MCPBusClient:
    """Lightweight client for registering the agent with the central MCP Bus.

    Args:
        base_url: Base URL of the MCP Bus (defaults to MCP_BUS_URL).
    """

    def __init__(self, base_url: str = MCP_BUS_URL) -> None:
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: List[str]) -> None:
        """Register an agent with the MCP bus.

        Raises:
            requests.exceptions.RequestException: If the registration HTTP call fails.
        """
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            response = requests.post(
                f"{self.base_url}/register", json=registration_data, timeout=(2, 5)
            )
            response.raise_for_status()
            logger.info("Successfully registered %s with MCP Bus.", agent_name)
        except requests.exceptions.RequestException:
            # Log full stack trace for diagnostics and re-raise
            logger.exception("Failed to register %s with MCP Bus.", agent_name)
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown context manager for the FastAPI app.

    Registers the agent with the MCP bus if available and sets the module
    readiness flag.
    """
    logger.info("Synthesizer agent is starting up.")
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
        logger.info("Registered tools with MCP Bus.")
    except Exception:
        logger.warning("MCP Bus unavailable; running in standalone mode.")

    # Note: Models will be downloaded automatically by HuggingFace transformers when first used

    global ready
    ready = True
    yield
    logger.info("Synthesizer agent is shutting down.")


app = FastAPI(lifespan=lifespan)

# Initialize metrics
metrics = JustNewsMetrics("synthesizer")
# Register the metrics middleware; metrics.request_middleware is a callable
app.middleware("http")(metrics.request_middleware)

# Register shutdown endpoint if available
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for synthesizer")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for synthesizer")


class ToolCall(BaseModel):
    """Standard MCP tool call format used by agent endpoints.

    Attributes:
        args: Positional arguments for the tool.
        kwargs: Keyword arguments for the tool.
    """

    args: List[Any] = Field(default_factory=list)
    kwargs: Dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> Dict[str, str]:
    """Liveness probe.

    Returns:
        A small JSON object indicating service liveness.
    """
    return {"status": "ok"}


@app.get("/ready")
def ready_endpoint() -> Dict[str, bool]:
    """Readiness probe.

    Returns:
        JSON object with readiness boolean.
    """
    return {"ready": ready}


# Metrics endpoint
@app.get("/metrics")
def get_metrics() -> Response:
    """Prometheus metrics endpoint.

    Returns:
        A plain text response containing Prometheus metrics.
    """
    return Response(content=metrics.get_metrics(), media_type="text/plain")


@app.post("/log_feedback")
def log_feedback(call: ToolCall) -> Dict[str, Any]:
    """Log feedback sent from other agents or tests.

    The function records a timestamped feedback entry and returns it.
    """
    try:
        feedback_data: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "feedback": call.kwargs.get("feedback"),
        }
        logger.info("Logging feedback: %s", feedback_data)
        return feedback_data
    except Exception:
        logger.exception("An error occurred while logging feedback")
        raise HTTPException(status_code=500, detail="Failed to log feedback")


@app.post("/aggregate_cluster")
def aggregate_cluster_endpoint(call: ToolCall) -> Any:
    """Aggregate a cluster of articles into a synthesis.

    Delegates to the local `tools.aggregate_cluster` implementation.
    """
    try:
        # Use relative import to resolve the agent-local tools module
        from .tools import aggregate_cluster as _aggregate_cluster

        logger.info("Calling aggregate_cluster with args: %s and kwargs: %s", call.args, call.kwargs)
        return _aggregate_cluster(*call.args, **call.kwargs)
    except Exception:
        logger.exception("An error occurred in aggregate_cluster")
        raise HTTPException(status_code=500, detail="aggregate_cluster failed")


@app.post("/cluster_articles")
def cluster_articles_endpoint(call: ToolCall) -> Any:
    """Cluster a list of articles into groups.

    Delegates to the local `tools.cluster_articles` implementation.
    """
    try:
        # Use relative import to resolve the agent-local tools module
        from .tools import cluster_articles as _cluster_articles

        logger.info("Calling cluster_articles with args: %s and kwargs: %s", call.args, call.kwargs)
        return _cluster_articles(*call.args, **call.kwargs)
    except Exception:
        logger.exception("An error occurred in cluster_articles")
        raise HTTPException(status_code=500, detail="cluster_articles failed")


@app.post("/neutralize_text")
def neutralize_text_endpoint(call: ToolCall) -> Any:
    """Neutralize text for bias and aggressive language.

    Delegates to the local `tools.neutralize_text` implementation.
    """
    try:
        # Use relative import to resolve the agent-local tools module
        from .tools import neutralize_text as _neutralize_text

        logger.info("Calling neutralize_text with args: %s and kwargs: %s", call.args, call.kwargs)
        return _neutralize_text(*call.args, **call.kwargs)
    except Exception:
        logger.exception("An error occurred in neutralize_text")
        raise HTTPException(status_code=500, detail="neutralize_text failed")


# GPU-accelerated endpoints (V4 performance implementation)
@app.post("/synthesize_news_articles_gpu")
def synthesize_news_articles_gpu_endpoint(call: ToolCall) -> Dict[str, Any]:
    """GPU-accelerated news article synthesis endpoint.

    Attempts to use GPU tools and falls back to CPU implementations when
    GPU tooling is unavailable or raises an error.
    """
    try:
        from .gpu_tools import synthesize_news_articles_gpu

        # Normalize input: support args[0] or kwargs['articles']
        articles: List[Dict[str, Any]] = []
        if call.args and len(call.args) > 0 and isinstance(call.args[0], list):
            articles = call.args[0]
        elif isinstance(call.kwargs.get("articles"), list):
            articles = call.kwargs.get("articles", [])

        logger.info("Calling GPU synthesize with %d articles", len(articles))
        # GPU tool in tools.py expects full article dicts and will handle fallback itself
        result = synthesize_news_articles_gpu(articles)

        # Log performance for monitoring
        if isinstance(result, dict) and result.get("success") and "performance" in result:
            perf = result["performance"]
            try:
                logger.info("GPU synthesis: %.1f articles/sec", float(perf.get("articles_per_sec", 0.0)))
            except Exception:
                logger.debug("Performance logging skipped: invalid perf data")

        return result
    except Exception:
        logger.exception("GPU synthesis error; attempting CPU fallback")
        # Graceful fallback to CPU implementation
        try:
            # Use relative import to resolve the agent-local tools module
            from .tools import aggregate_cluster as _aggregate_cluster
            from .tools import cluster_articles as _cluster_articles

            logger.info("Falling back to CPU synthesis")
            # Prepare article texts for CPU-only tools which expect list[str]
            articles: List[Dict[str, Any]] = []
            if call.args and len(call.args) > 0 and isinstance(call.args[0], list):
                articles = call.args[0]
            elif isinstance(call.kwargs.get("articles"), list):
                articles = call.kwargs.get("articles", [])

            article_texts: List[str] = [a.get("content", "") for a in articles if isinstance(a, dict)]

            # cluster_articles returns a dict with 'clusters' key
            clusters_result = _cluster_articles(article_texts)
            clusters = clusters_result.get("clusters", []) if isinstance(clusters_result, dict) else []

            themes: List[Dict[str, Any]] = []
            syntheses: List[Any] = []
            for i, cluster_indices in enumerate(clusters):
                # cluster_indices is a list of indices into article_texts
                cluster_texts = [article_texts[idx] for idx in cluster_indices if 0 <= idx < len(article_texts)]
                aggregation = _aggregate_cluster(cluster_texts)
                syntheses.append(aggregation)
                theme_articles = [articles[idx] for idx in cluster_indices if 0 <= idx < len(articles)]
                themes.append({"theme_name": f"theme_{i}", "articles": theme_articles, "synthesis": aggregation})

            overall_synthesis = {"clusters": syntheses}
            return {
                "success": True,
                "themes": themes,
                "synthesis": overall_synthesis,
                "performance": {"articles_per_sec": 1.0, "gpu_used": False},
            }
        except Exception:
            logger.exception("CPU fallback failed for GPU synthesis")
            raise HTTPException(status_code=500, detail="GPU synthesis and CPU fallback both failed")


@app.post("/get_synthesizer_performance")
def get_synthesizer_performance_endpoint(call: ToolCall) -> Dict[str, Any]:
    """Get synthesizer performance statistics.

    Returns a dictionary with basic counters when GPU tooling is unavailable.
    """
    try:
        from .gpu_tools import get_synthesizer_performance

        logger.info("Retrieving synthesizer performance stats")
        # get_synthesizer_performance takes no arguments in tools.py
        return get_synthesizer_performance()
    except Exception:
        logger.exception("Performance stats error")
        # Return basic stats if GPU tools unavailable
        return {
            "total_processed": 0,
            "gpu_processed": 0,
            "cpu_processed": 0,
            "gpu_allocated": False,
            "models_loaded": False,
            "error": "GPU tooling unavailable",
        }


# MCP compatibility alias: older clients may call /synthesize_content
@app.post("/synthesize_content")
def synthesize_content_alias(call: ToolCall) -> Any:
    """Alias for compatibility with existing E2E tests; delegates to GPU implementation."""
    try:
        # Reuse GPU pathway for best performance; args/kwargs are identical
        return synthesize_news_articles_gpu_endpoint(call)
    except Exception:
        logger.exception("synthesize_content alias failed")
        raise HTTPException(status_code=500, detail="synthesize_content failed")


if __name__ == "__main__":
    import uvicorn

    host: str = os.environ.get("SYNTHESIZER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("SYNTHESIZER_PORT", SYNTHESIZER_AGENT_PORT))

    logger.info("Starting Synthesizer Agent on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
