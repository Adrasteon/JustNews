"""
Main file for the Crawler Agent.
"""
# main.py for Crawler Agent

import os
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from fastapi import FastAPI, HTTPException, BackgroundTasks
from typing import Dict, Any
import uuid
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from common.observability import get_logger
from common.metrics import JustNewsMetrics

# Configure logging
logger = get_logger(__name__)

ready = False
# In-memory storage of crawl job statuses
crawl_jobs: Dict[str, Any] = {}

# Environment variables
CRAWLER_AGENT_PORT = int(os.environ.get("CRAWLER_AGENT_PORT", 8015))  # Updated to 8015 per canonical port mapping
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
    logger.info("Crawler agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="crawler",
            agent_address=f"http://localhost:{CRAWLER_AGENT_PORT}",
            tools=[
                "unified_production_crawl",
                "get_crawler_info",
                "get_performance_metrics"
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield
    logger.info("Crawler agent is shutting down.")

app = FastAPI(lifespan=lifespan, title="Crawler Agent", description="Unified production crawling agent")

# Initialize metrics
metrics = JustNewsMetrics("crawler")

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

@app.post("/unified_production_crawl")
async def unified_production_crawl_endpoint(call: ToolCall, background_tasks: BackgroundTasks):
    """
    Enqueue a background unified production crawl job and return immediately with a job ID.
    """
    # Generate a unique job identifier
    job_id = uuid.uuid4().hex
    # Initialize job status
    crawl_jobs[job_id] = {"status": "pending"}
    # Extract parameters
    domains = call.args[0] if call.args else call.kwargs.get("domains", [])
    max_articles = call.kwargs.get("max_articles_per_site", 25)
    concurrent = call.kwargs.get("concurrent_sites", 3)
    logger.info(f"Enqueueing background crawl job {job_id} for {len(domains)} domains")
    # Define background task
    async def _crawl_task(domains, max_articles, concurrent, job_id):
        from agents.crawler.unified_production_crawler import UnifiedProductionCrawler
        try:
            crawl_jobs[job_id]["status"] = "running"
            async with UnifiedProductionCrawler() as crawler:
                await crawler._load_ai_models()
                result = await crawler.run_unified_crawl(domains, max_articles, concurrent)
            # Store result in job status
            crawl_jobs[job_id] = {"status": "completed", "result": result}
            logger.info(f"Background crawl {job_id} complete. Articles: {len(result.get('articles', []))}")
        except Exception as e:
            crawl_jobs[job_id] = {"status": "failed", "error": str(e)}
            logger.error(f"Background crawl {job_id} failed: {e}")
    # Schedule the task
    background_tasks.add_task(_crawl_task, domains, max_articles, concurrent, job_id)
    # Return accepted status with job ID
    return JSONResponse(status_code=202, content={"status": "accepted", "job_id": job_id})

@app.get("/job_status/{job_id}")
def job_status(job_id: str):
    """Retrieve status and result (if completed) for a crawl job."""
    if job_id not in crawl_jobs:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return crawl_jobs[job_id]

@app.get("/jobs")
def list_jobs():
    """List all current crawl job IDs with their status (without full results)."""
    # Return a mapping of job_id to status only for brevity
    return {job_id: info.get("status") for job_id, info in crawl_jobs.items()}

@app.post("/clear_jobs")
def clear_jobs():
    """Clear completed and failed jobs from memory."""
    global crawl_jobs
    cleared_jobs = []
    for job_id in list(crawl_jobs.keys()):
        del crawl_jobs[job_id]
        cleared_jobs.append(job_id)
    
    return {"cleared_jobs": cleared_jobs, "message": f"Cleared {len(cleared_jobs)} jobs from memory"}

@app.post("/reset_crawler")
def reset_crawler():
    """Completely reset the crawler state - clear all jobs and reset performance metrics."""
    global crawl_jobs
    
    # Clear all jobs
    cleared_jobs = list(crawl_jobs.keys())
    crawl_jobs.clear()
    
    # Reset performance metrics if they exist
    try:
        from agents.crawler.performance_monitoring import reset_performance_metrics
        reset_performance_metrics()
    except ImportError:
        pass  # Performance monitoring might not be available
    
    return {
        "cleared_jobs": cleared_jobs, 
        "message": f"Completely reset crawler: cleared {len(cleared_jobs)} jobs and reset metrics"
    }

@app.post("/get_crawler_info")
def get_crawler_info_endpoint(call: ToolCall):
    try:
        from agents.crawler.unified_production_crawler import get_crawler_info
        logger.info(f"Calling get_crawler_info with args: {call.args} and kwargs: {call.kwargs}")
        return get_crawler_info(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in get_crawler_info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_performance_metrics")
def get_performance_metrics_endpoint(call: ToolCall):
    try:
        from agents.crawler.performance_monitoring import get_performance_monitor
        monitor = get_performance_monitor()
        logger.info(f"Calling get_performance_metrics with args: {call.args} and kwargs: {call.kwargs}")
        return monitor.get_current_metrics()
    except Exception as e:
        logger.error(f"An error occurred in get_performance_metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready_endpoint():
    return {"ready": ready}

@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Crawler Agent on port {CRAWLER_AGENT_PORT}")
    uvicorn.run(
        "agents.crawler.main:app",
        host="0.0.0.0",
        port=CRAWLER_AGENT_PORT,
        reload=False,
        log_level="info"
    )
