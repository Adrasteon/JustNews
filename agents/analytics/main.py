"""
Main file for the Analytics Agent.
"""
# main.py for Analytics Agent

import os
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.analytics.dashboard import create_analytics_app
from common.observability import get_logger
from common.metrics import JustNewsMetrics

# Configure logging
logger = get_logger(__name__)

ready = False

# Environment variables
ANALYTICS_AGENT_PORT = int(os.environ.get("ANALYTICS_AGENT_PORT", 8011))
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
    logger.info("Analytics agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="analytics",
            agent_address=f"http://localhost:{ANALYTICS_AGENT_PORT}",
            tools=["get_system_health", "get_performance_metrics", "get_agent_profile", "get_optimization_recommendations"],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield

    logger.info("Analytics agent is shutting down.")

# Initialize FastAPI with the lifespan context manager
app = FastAPI(title="Analytics Agent", lifespan=lifespan)

# Initialize metrics
metrics = JustNewsMetrics("analytics")
app.middleware("http")(metrics.request_middleware)

# Register common shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for analytics")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for analytics")

# Include the analytics dashboard routes
analytics_dashboard = create_analytics_app()
app.mount("/dashboard", analytics_dashboard, name="analytics-dashboard")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready_endpoint():
    return {"ready": ready}

# Metrics endpoint
@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi import Response
    return Response(content=metrics.get_metrics(), media_type="text/plain")

# Pydantic models
class ToolCall(BaseModel):
    args: list
    kwargs: dict

class PerformanceMetrics(BaseModel):
    agent_name: str
    operation: str
    processing_time_s: float
    batch_size: int
    success: bool
    gpu_memory_allocated_mb: float = 0.0
    gpu_memory_reserved_mb: float = 0.0
    gpu_utilization_pct: float = 0.0
    temperature_c: float = 0.0
    power_draw_w: float = 0.0
    throughput_items_per_s: float = 0.0

@app.post("/get_system_health")
def get_system_health(call: ToolCall):
    """Get comprehensive system health metrics"""
    try:
        from agents.common.advanced_analytics import get_analytics_engine

        analytics_engine = get_analytics_engine()
        health = analytics_engine.get_system_health_score()

        logger.info("Retrieved system health metrics")
        return {"status": "success", "data": health}
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_performance_metrics")
def get_performance_metrics(call: ToolCall):
    """Get real-time performance metrics for specified time period"""
    try:
        from agents.common.advanced_analytics import get_analytics_engine

        kwargs = call.kwargs or {}
        hours = kwargs.get("hours", 1)

        if hours < 1 or hours > 24:
            raise HTTPException(status_code=400, detail="Hours must be between 1 and 24")

        analytics_engine = get_analytics_engine()
        analytics = analytics_engine.get_real_time_analytics(hours=hours)

        logger.info(f"Retrieved performance metrics for {hours} hours")
        return {"status": "success", "data": analytics.__dict__}
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_agent_profile")
def get_agent_profile(call: ToolCall):
    """Get performance profile for specific agent"""
    try:
        from agents.common.advanced_analytics import get_analytics_engine

        kwargs = call.kwargs or {}
        agent_name = kwargs.get("agent_name")
        hours = kwargs.get("hours", 24)

        if not agent_name:
            raise HTTPException(status_code=400, detail="agent_name is required")

        if hours < 1 or hours > 168:  # Max 1 week
            raise HTTPException(status_code=400, detail="Hours must be between 1 and 168")

        analytics_engine = get_analytics_engine()
        profile = analytics_engine.get_agent_performance_profile(agent_name, hours=hours)

        logger.info(f"Retrieved profile for agent {agent_name}")
        return {"status": "success", "data": profile}
    except Exception as e:
        logger.error(f"Error getting agent profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_optimization_recommendations")
def get_optimization_recommendations(call: ToolCall):
    """Get advanced optimization recommendations"""
    try:
        from agents.common.advanced_optimization import generate_optimization_recommendations

        kwargs = call.kwargs or {}
        hours = kwargs.get("hours", 24)

        recommendations = generate_optimization_recommendations(hours)

        result = [
            {
                "id": rec.id,
                "category": rec.category.value,
                "priority": rec.priority.value,
                "title": rec.title,
                "description": rec.description,
                "impact_score": rec.impact_score,
                "confidence_score": rec.confidence_score,
                "complexity": rec.implementation_complexity,
                "time_savings": rec.estimated_time_savings,
                "affected_agents": rec.affected_agents,
                "steps": rec.implementation_steps
            }
            for rec in recommendations
        ]

        logger.info(f"Generated {len(result)} optimization recommendations")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/record_performance_metric")
def record_performance_metric(call: ToolCall):
    """Record a custom performance metric"""
    try:
        from agents.common.advanced_analytics import get_analytics_engine, PerformanceMetrics
        from datetime import datetime

        kwargs = call.kwargs or {}

        # Validate required fields
        required_fields = ["agent_name", "operation", "processing_time_s", "batch_size", "success"]
        for field in required_fields:
            if field not in kwargs:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        # Create metric object
        metric = PerformanceMetrics(
            timestamp=datetime.now(),
            agent_name=kwargs["agent_name"],
            operation=kwargs["operation"],
            processing_time_s=float(kwargs["processing_time_s"]),
            batch_size=int(kwargs["batch_size"]),
            success=bool(kwargs["success"]),
            gpu_memory_allocated_mb=float(kwargs.get("gpu_memory_allocated_mb", 0.0)),
            gpu_memory_reserved_mb=float(kwargs.get("gpu_memory_reserved_mb", 0.0)),
            gpu_utilization_pct=float(kwargs.get("gpu_utilization_pct", 0.0)),
            temperature_c=float(kwargs.get("temperature_c", 0.0)),
            power_draw_w=float(kwargs.get("power_draw_w", 0.0)),
            throughput_items_per_s=float(kwargs.get("throughput_items_per_s", 0.0))
        )

        # Record the metric
        analytics_engine = get_analytics_engine()
        analytics_engine.record_metric(metric)

        logger.info(f"Recorded performance metric for {kwargs['agent_name']}")
        return {"status": "success", "message": "Metric recorded successfully"}
    except Exception as e:
        logger.error(f"Error recording performance metric: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=ANALYTICS_AGENT_PORT)
