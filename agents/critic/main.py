"""
Main file for the Critic Agent.

IMPORTANT: Bias detection functionality has been centralized in Scout V2 Agent
for consistency and improved performance. Critic Agent now focuses on:

- Editorial logic and argument structure analysis
- Content synthesis critique 
- Neutrality assessment and factual consistency
- Logical fallacy detection (future enhancement)

For bias detection, use Scout V2 Agent endpoints:
- POST /comprehensive_content_analysis (includes bias detection)
- POST /detect_bias (dedicated bias detection)
"""
# main.py for Critic Agent

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

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
CRITIC_AGENT_PORT = int(os.environ.get("CRITIC_AGENT_PORT", 8006))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

class MCPBusClient:
    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list):
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            response = requests.post(f"{self.base_url}/register", json=registration_data, timeout=(2, 5))
            response.raise_for_status()
            logger.info(f"Successfully registered {agent_name} with MCP Bus.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register {agent_name} with MCP Bus: {e}")
            raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Critic agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="critic",
            agent_address=f"http://localhost:{CRITIC_AGENT_PORT}",
            tools=["critique_synthesis", "critique_neutrality",
                   "critique_content_gpu", "get_critic_performance"],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield
    logger.info("Critic agent is shutting down.")

app = FastAPI(lifespan=lifespan)

# Initialize metrics
metrics = JustNewsMetrics("critic")

# Register shutdown endpoint if available
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for critic")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for critic")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready_endpoint():
    return {"ready": ready}


@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    return Response(metrics.get_metrics(), media_type="text/plain")

class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]

@app.post("/critique_synthesis")
def critique_synthesis(call: ToolCall):
    try:
        from .tools import critique_synthesis
        logger.info(f"Calling critique_synthesis with args: {call.args} and kwargs: {call.kwargs}")
        return critique_synthesis(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in critique_synthesis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/critique_neutrality")
def critique_neutrality(call: ToolCall):
    try:
        from .tools import critique_neutrality
        logger.info(f"Calling critique_neutrality with args: {call.args} and kwargs: {call.kwargs}")
        return critique_neutrality(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in critique_neutrality: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add feedback logging for Critic Agent
@app.post("/log_feedback")
def log_feedback(call: ToolCall):
    try:
        feedback_data = {
            "timestamp": datetime.now().isoformat(),
            "feedback": call.kwargs.get("feedback")
        }
        logger.info(f"Logging feedback: {feedback_data}")
        return feedback_data
    except Exception as e:
        logger.error(f"An error occurred while logging feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# GPU-accelerated endpoints (V4 performance implementation)
@app.post("/critique_content_gpu")
def critique_content_gpu_endpoint(call: ToolCall):
    """GPU-accelerated content critique endpoint"""
    try:
        from .gpu_tools import critique_content_gpu
        logger.info(f"Calling GPU critique with {len(call.args[0]) if call.args else 0} articles")
        result = critique_content_gpu(*call.args, **call.kwargs)

        # Log performance for monitoring
        if result.get('success') and 'performance' in result:
            perf = result['performance']
            logger.info(f"✅ GPU critique: {perf['articles_per_sec']:.1f} articles/sec")

        return result
    except Exception as e:
        logger.error(f"❌ GPU critique error: {e}")
        # Graceful fallback to CPU implementation
        try:
            from .tools import critique_neutrality, critique_synthesis
            logger.info("🔄 Falling back to CPU critique")
            # Simple fallback implementation
            articles = call.args[0] if call.args else []
            critiques = []
            for article in articles:
                synthesis_critique = critique_synthesis(article.get('content', ''))
                neutrality_critique = critique_neutrality(article.get('content', ''))
                critiques.append({
                    'article_title': article.get('title', 'Unknown'),
                    'critique': f"Synthesis: {synthesis_critique}\nNeutrality: {neutrality_critique}",
                    'quality_score': 0.5,
                    'bias_indicators': [],
                    'accuracy_flags': []
                })
            return {
                "success": True,
                "critiques": critiques,
                "performance": {"articles_per_sec": 1.0, "gpu_used": False}
            }
        except Exception as fallback_error:
            logger.error(f"❌ CPU fallback failed: {fallback_error}")
            raise HTTPException(status_code=500, detail=f"GPU critique failed: {e}, CPU fallback failed: {fallback_error}")

@app.post("/get_critic_performance")
def get_critic_performance_endpoint(call: ToolCall):
    """Get critic performance statistics"""
    try:
        from .gpu_tools import get_critic_performance
        logger.info("Retrieving critic performance stats")
        return get_critic_performance(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"❌ Performance stats error: {e}")
        # Return basic stats if GPU tools unavailable
        return {
            "total_processed": 0,
            "gpu_processed": 0,
            "cpu_processed": 0,
            "gpu_allocated": False,
            "models_loaded": False,
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    import os

    host = os.environ.get("CRITIC_HOST", "0.0.0.0")
    port = int(os.environ.get("CRITIC_PORT", 8006))

    logger.info(f"Starting Critic Agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
