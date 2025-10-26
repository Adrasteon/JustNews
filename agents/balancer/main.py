"""
Main file for the Balancer Agent.
Load balancing and workload distribution agent with MCP integration.
"""
# main.py for Balancer Agent

import os
from contextlib import asynccontextmanager
from typing import Dict, Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from common.observability import get_logger
from common.metrics import JustNewsMetrics
from .balancer_engine import BalancerEngine
from .tools import distribute_load, get_agent_status, balance_workload, monitor_performance

# Configure logging
logger = get_logger(__name__)

ready = False

# Environment variables
BALANCER_AGENT_PORT = int(os.environ.get("BALANCER_AGENT_PORT", 8010))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Security configuration
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")

class MCPBusClient:
    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list):
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            response = requests.post(f"{self.base_url}/register", json=registration_data, timeout=(1, 2))
            response.raise_for_status()
            logger.info(f"Successfully registered {agent_name} with MCP Bus.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register {agent_name} with MCP Bus: {e}")
            raise

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

app = FastAPI(lifespan=lifespan, title="Balancer Agent", description="Load balancing and workload distribution agent")

# Initialize metrics
metrics = JustNewsMetrics("balancer")

# Security middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Metrics middleware (must be added after CORS middleware)
app.middleware("http")(metrics.request_middleware)

class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]

@app.post("/distribute_load")
def distribute_load_endpoint(call: ToolCall):
    """Distribute workload across available agents"""
    try:
        result = distribute_load(*call.args, **call.kwargs)
        logger.info("Load distributed successfully")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error distributing load: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_agent_status")
def get_agent_status_endpoint(call: ToolCall):
    """Get status of all agents for load balancing"""
    try:
        result = get_agent_status(*call.args, **call.kwargs)
        logger.info("Retrieved agent status")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error getting agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/balance_workload")
def balance_workload_endpoint(call: ToolCall):
    """Balance workload based on agent capacity and performance"""
    try:
        result = balance_workload(*call.args, **call.kwargs)
        logger.info("Workload balanced successfully")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error balancing workload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/monitor_performance")
def monitor_performance_endpoint(call: ToolCall):
    """Monitor agent performance for load balancing decisions"""
    try:
        result = monitor_performance(*call.args, **call.kwargs)
        logger.info("Performance monitoring completed")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error monitoring performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "agent": "balancer"}

@app.get("/ready")
def ready_endpoint():
    return {"ready": ready}

@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Balancer Agent on port {BALANCER_AGENT_PORT}")
    uvicorn.run(
        "agents.balancer.main:app",
        host="0.0.0.0",
        port=BALANCER_AGENT_PORT,
        reload=False,
        log_level="info"
    )