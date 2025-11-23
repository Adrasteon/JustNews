"""
GPU Orchestrator - FastAPI application for GPU management and model preloading.

This module provides the REST API endpoints for GPU orchestration including:
- GPU telemetry and monitoring
- GPU lease allocation and management
- Model preloading with background job management
- Policy configuration and health checks
- MCP Bus integration for inter-agent communication
"""

import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .gpu_orchestrator_engine import engine
from .tools import (
    get_allocations,
    get_gpu_info,
    get_metrics,
    get_mps_allocation,
    get_policy,
    lease_gpu,
    models_preload,
    models_status,
    release_gpu_lease,
    set_policy,
)

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

# Constants
GPU_ORCHESTRATOR_PORT = int(os.environ.get("GPU_ORCHESTRATOR_PORT", "8008"))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
SAFE_MODE = os.environ.get("SAFE_MODE", "false").lower() == "true"

# Global state
READINESS = False


class MCPBusClient:
    """Client for MCP Bus communication."""

    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list[str]):
        """Register agent with MCP Bus."""
        try:
            import requests
        except Exception:
            engine.logger.warning("Requests library not available; skipping MCP Bus registration attempt")
            return

        registration_data = {
            "name": agent_name,
            "address": agent_address,
            "tools": tools,
        }

        for attempt in range(5):  # Retry up to 5 times
            try:
                response = requests.post(
                    f"{self.base_url}/register",
                    json=registration_data,
                    timeout=(2, 5)
                )
                response.raise_for_status()
                engine.logger.info(f"Successfully registered {agent_name} with MCP Bus on attempt {attempt + 1}")
                return
            except requests.exceptions.RequestException as e:
                engine.logger.warning(f"MCP Bus unavailable for registration (attempt {attempt + 1}/5): {e}")
                time.sleep(2 ** attempt)  # Exponential backoff

        engine.logger.error(f"Failed to register {agent_name} with MCP Bus after multiple attempts.")


class PolicyUpdate(BaseModel):
    """GPU policy update model."""
    max_memory_per_agent_mb: int | None = Field(None, ge=256, description="Per-agent memory cap in MB")
    allow_fractional_shares: bool | None = None
    kill_on_oom: bool | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class LeaseRequest(BaseModel):
    """GPU lease request model."""
    agent: str
    min_memory_mb: int | None = Field(0, ge=0)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ReleaseRequest(BaseModel):
    """GPU lease release request model."""
    token: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PreloadRequest(BaseModel):
    """Model preload request model."""
    agents: list[str] | None = Field(default=None, description="Subset of agents to preload; default all from AGENT_MODEL_MAP.json")
    refresh: bool = Field(default=False, description="Restart preloading even if a job already completed")
    strict: bool | None = Field(default=None, description="Override STRICT_MODEL_STORE env for this preload run")

    model_config = ConfigDict(arbitrary_types_allowed=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global READINESS
    engine.logger.info("GPU Orchestrator starting up")

    # Registration status tracker
    registration_complete = threading.Event()

    def register_agent_background(agent_name: str, agent_address: str, tools: list[str]):
        """Register the agent with the MCP Bus in a background thread."""
        def background_task():
            client = MCPBusClient()
            client.register_agent(agent_name, agent_address, tools)
            registration_complete.set()  # Signal registration completion

        thread = threading.Thread(target=background_task, daemon=True)
        thread.start()

    # Start background registration
    register_agent_background(
        agent_name="gpu_orchestrator",
        agent_address=f"http://localhost:{GPU_ORCHESTRATOR_PORT}",
        tools=[
            "health",
            "gpu_info",
            "get_policy",
            "set_policy",
            "get_allocations",
            "lease",
            "release",
            "models_preload",
            "models_status",
            "mps_allocation",
        ],
    )

    # Wait for registration to complete before signaling readiness
    engine.logger.info("Waiting for MCP Bus registration to complete...")
    registration_complete.wait(timeout=30)  # Wait up to 30 seconds
    if registration_complete.is_set():
        engine.logger.info("MCP Bus registration completed successfully.")
    else:
        engine.logger.warning("MCP Bus registration did not complete within the timeout.")

    READINESS = True
    yield
    engine.logger.info("GPU Orchestrator shutting down")


# Create FastAPI app
app = FastAPI(title="GPU Orchestrator", lifespan=lifespan)

# Add metrics middleware
app.middleware("http")(engine.metrics.request_middleware)

# Optional shared endpoints
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    engine.logger.debug("shutdown endpoint not registered for gpu_orchestrator")

try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    engine.logger.debug("reload endpoint not registered for gpu_orchestrator")


@app.get("/health")
@app.post("/health")
async def health(request: Request):
    """Health check endpoint."""
    return {"status": "ok", "safe_mode": SAFE_MODE}


@app.get("/ready")
def ready():
    """Readiness check endpoint."""
    return {"ready": READINESS}


@app.get("/gpu/info")
def gpu_info_endpoint():
    """Return current GPU telemetry (read-only)."""
    try:
        data = get_gpu_info()

        if not engine._NVML_SUPPORTED:
            data["nvml_init_error"] = engine._NVML_INIT_ERROR or "unsupported"
            engine.logger.warning(f"NVML not supported: {data['nvml_init_error']}")

        return data
    except Exception as e:
        engine.logger.error(f"Failed to get GPU snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/policy")
def get_policy_endpoint():
    """Get current GPU policy."""
    return get_policy()


@app.post("/policy")
def set_policy_endpoint(update: PolicyUpdate):
    """Update GPU policy."""
    return set_policy(
        max_memory_per_agent_mb=update.max_memory_per_agent_mb,
        allow_fractional_shares=update.allow_fractional_shares,
        kill_on_oom=update.kill_on_oom
    )


@app.get("/allocations")
def get_allocations_endpoint():
    """Return current agent→GPU allocation view."""
    return get_allocations()


@app.post("/lease")
def lease_endpoint(req: LeaseRequest):
    """Obtain a simple ephemeral GPU lease."""
    return lease_gpu(req.agent, req.min_memory_mb)


@app.post("/release")
def release_endpoint(req: ReleaseRequest):
    """Release a GPU lease."""
    return release_gpu_lease(req.token)


@app.post("/models/preload")
def models_preload_endpoint(req: PreloadRequest):
    """Start a background model preload job."""
    return models_preload(req.agents, req.refresh, req.strict)


@app.post("/workers/pool")
def create_worker_pool(agent: str | None = None, model: str | None = None, adapter: str | None = None, num_workers: int = 1, hold_seconds: int = 600):
    """Create a named worker pool. `agent` is an optional name used to derive an id when omitted."""
    pool_id = agent or f"pool_{int(time.time())}"
    try:
        return engine.start_worker_pool(pool_id=pool_id, model_id=model, adapter=adapter, num_workers=num_workers, hold_seconds=hold_seconds)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workers/pool")
def list_pools():
    return engine.list_worker_pools()


@app.delete("/workers/pool/{pool_id}")
def delete_pool(pool_id: str):
    try:
        return engine.stop_worker_pool(pool_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_pool")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models/status")
def models_status_endpoint():
    """Return current model preload status."""
    return models_status()


@app.get("/mps/allocation")
def get_mps_allocation_endpoint():
    """Return MPS resource allocation configuration."""
    return get_mps_allocation()


@app.get("/metrics")
def get_metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(get_metrics(), media_type="text/plain")


@app.get("/tools")
def list_tools_endpoint():
    """List all tools exposed by the GPU Orchestrator."""
    return {"tools": [
        "health",
        "gpu_info",
        "get_policy",
        "set_policy",
        "get_allocations",
        "lease",
        "release",
        "models_preload",
        "models_status",
        "mps_allocation"
    ]}


@app.post("/notify_ready")
def notify_ready_endpoint():
    """Handle notification from MCP Bus that it is ready."""
    try:
        client = MCPBusClient()
        client.register_agent(
            agent_name="gpu_orchestrator",
            agent_address=f"http://localhost:{GPU_ORCHESTRATOR_PORT}",
            tools=[
                "health",
                "gpu_info",
                "get_policy",
                "set_policy",
                "get_allocations",
                "lease",
                "release",
                "models_preload",
                "models_status",
                "mps_allocation",
            ],
        )
        engine.logger.info("Successfully registered GPU Orchestrator with MCP Bus after notification.")
    except Exception as e:
        engine.logger.error(f"Failed to register GPU Orchestrator with MCP Bus: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@app.on_event("startup")
async def orchestrator_startup():
    """Initialize GPU orchestrator on startup."""
    engine.logger.info("Starting GPU Orchestrator...")
    engine.initialize_nvml()
    engine.logger.info("GPU Orchestrator startup sequence complete.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=GPU_ORCHESTRATOR_PORT)


# Backwards-compatibility: expose ALLOCATIONS at module level for tests that import it
try:
    try:
        ALLOCATIONS = get_allocations()
    except Exception:
        # Fall back to an empty allocation mapping if retrieving allocations fails at import-time
        ALLOCATIONS = {}
except NameError:
    # If get_allocations isn't available for some reason, expose an empty dict
    ALLOCATIONS = {}
