"""
Main file for the Chief Editor Agent.
"""
# main.py for Chief Editor Agent

import os
from contextlib import asynccontextmanager
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.chief_editor.handler import handle_review_request
from common.observability import get_logger

# Import metrics library
from common.metrics import JustNewsMetrics

# Configure logging

logger = get_logger(__name__)

ready = False

# Environment variables
CHIEF_EDITOR_AGENT_PORT = int(os.environ.get("CHIEF_EDITOR_AGENT_PORT", 8001))
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
    logger.info("Chief Editor agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="chief_editor",
            agent_address=f"http://localhost:{CHIEF_EDITOR_AGENT_PORT}",
            tools=["request_story_brief", "publish_story", "review_evidence"],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield

    logger.info("Chief Editor agent is shutting down.")

# Initialize FastAPI with the lifespan context manager
app = FastAPI(title="Chief Editor Agent", lifespan=lifespan)

# Initialize metrics
metrics = JustNewsMetrics("chief_editor")

# Register common shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for chief_editor")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for chief_editor")

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

# Pydantic models
class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]

class StoryBrief(BaseModel):
    topic: str
    deadline: str
    priority: str

@app.post("/request_story_brief")
def request_story_brief(call: ToolCall):
    """Request a story brief from another agent"""
    try:
        # Implementation for requesting story briefs
        logger.info("Requesting story brief")
        return {"status": "success", "message": "Story brief requested"}
    except Exception as e:
        logger.error(f"Error requesting story brief: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/publish_story")
def publish_story(call: ToolCall):
    """Publish a finalized story"""
    try:
        # Implementation for publishing stories
        logger.info("Publishing story")
        return {"status": "success", "message": "Story published"}
    except Exception as e:
        logger.error(f"Error publishing story: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/coordinate_editorial_workflow")
def coordinate_editorial_workflow(call: ToolCall):
    """Coordinate the editorial workflow between agents"""
    try:
        # Implementation for coordinating workflow
        logger.info("Coordinating editorial workflow")
        return {"status": "success", "message": "Workflow coordinated"}
    except Exception as e:
        logger.error(f"Error coordinating workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/manage_content_lifecycle")
def manage_content_lifecycle(call: ToolCall):
    """Manage the lifecycle of content through the system"""
    try:
        # Implementation for managing content lifecycle
        logger.info("Managing content lifecycle")
        return {"status": "success", "message": "Content lifecycle managed"}
    except Exception as e:
        logger.error(f"Error managing content lifecycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/review_evidence")
def review_evidence(call: ToolCall):
    """Endpoint to receive evidence review requests from other agents.

    Expected kwargs: evidence_manifest (path), reason
    Persists the request to a local JSONL queue for human reviewers or UI to pick up.
    """
    try:
        kwargs = call.kwargs or {}
        return handle_review_request(kwargs)
    except Exception as e:
        logger.error(f"Error enqueuing evidence review: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=CHIEF_EDITOR_AGENT_PORT)
