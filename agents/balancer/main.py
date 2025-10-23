"""
Main file for the Balancer Agent.
"""
# main.py for Balancer Agent

import os
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.balancer import tools
from common.observability import get_logger

# Import metrics library
from common.metrics import JustNewsMetrics

# Configure logging
logger = get_logger(__name__)

ready = False

# Environment variables
BALANCER_AGENT_PORT = int(os.environ.get("BALANCER_AGENT_PORT", 8010))
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

# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Balancer agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="balancer",
            agent_address=f"http://localhost:{BALANCER_AGENT_PORT}",
            tools=["distribute_load", "get_agent_status", "balance_workload", "monitor_performance"],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield

    logger.info("Balancer agent is shutting down.")

# Initialize FastAPI with the lifespan context manager
app = FastAPI(title="Balancer Agent", lifespan=lifespan)

# Initialize metrics
metrics = JustNewsMetrics("balancer")

# Register common shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for balancer")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for balancer")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)

@app.get("/health")
def health():
    return {"status": "ok", "agent": "balancer"}

@app.get("/ready")
def ready_endpoint():
    return {"ready": ready}


@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    return Response(metrics.get_metrics(), media_type="text/plain")

# Pydantic models
class ToolCall(BaseModel):
    args: list = []
    kwargs: dict = {}

@app.post("/distribute_load")
def distribute_load(call: ToolCall):
    """Distribute workload across available agents"""
    try:
        result = tools.distribute_load(*call.args, **call.kwargs)
        logger.info("Load distributed successfully")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error distributing load: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_agent_status")
def get_agent_status(call: ToolCall):
    """Get status of all agents for load balancing"""
    try:
        result = tools.get_agent_status(*call.args, **call.kwargs)
        logger.info("Retrieved agent status")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error getting agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/balance_workload")
def balance_workload(call: ToolCall):
    """Balance workload based on agent capacity and performance"""
    try:
        result = tools.balance_workload(*call.args, **call.kwargs)
        logger.info("Workload balanced successfully")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error balancing workload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/monitor_performance")
def monitor_performance(call: ToolCall):
    """Monitor agent performance for load balancing decisions"""
    try:
        result = tools.monitor_performance(*call.args, **call.kwargs)
        logger.info("Performance monitoring completed")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error monitoring performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=BALANCER_AGENT_PORT)

