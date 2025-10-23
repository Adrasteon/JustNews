#!/usr/bin/env python3
"""
Web Interface for JustNews Crawler Dashboard
"""

import os
import requests
import re
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import database functions
import sys
sys.path.append('/home/adra/justnewsagent/JustNewsAgent')
from agents.common.database import execute_query, initialize_connection_pool
from common.dev_db_fallback import apply_test_db_env_fallback

# Apply database environment fallback for development
apply_test_db_env_fallback()

# Initialize database connection pool
initialize_connection_pool()

def get_sources_with_limit(limit: int = None) -> list[str]:
    """Get active sources from database, optionally limited"""
    try:
        query = """
            SELECT domain
            FROM public.sources
            WHERE last_verified IS NOT NULL
            AND last_verified > now() - interval '30 days'
            ORDER BY last_verified DESC, name ASC
        """
        if limit:
            query += f" LIMIT {limit}"

        sources = execute_query(query)
        domains = [source['domain'] for source in sources]
        return domains

    except Exception as e:
        print(f"❌ Failed to query sources from database: {e}")
        return []

app = FastAPI(title="JustNews Crawler Dashboard")

# Environment variables
CRAWLER_AGENT_URL = os.environ.get("CRAWLER_AGENT_URL", "http://localhost:8015")
ANALYST_AGENT_URL = os.environ.get("ANALYST_AGENT_URL", "http://localhost:8004")
MEMORY_AGENT_URL = os.environ.get("MEMORY_AGENT_URL", "http://localhost:8007")
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

class CrawlRequest(BaseModel):
    domains: str  # Changed from list[str] to str to handle special commands
    max_sites: int = 5
    max_articles_per_site: int = 10
    concurrent_sites: int = 3
    strategy: str = "auto"
    enable_ai: bool = True
    timeout: int = 300
    user_agent: str = "JustNewsAgent/1.0"

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard HTML"""
    try:
        with open("/home/adra/justnewsagent/JustNewsAgent/agents/dashboard/web_interface/index.html", "r") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return "<html><body><h1>Error loading dashboard</h1></body></html>"

@app.get("/favicon.ico")
async def favicon():
    """Serve a simple favicon"""
    # Return a simple transparent 16x16 favicon
    # This is a minimal 16x16 transparent PNG favicon
    favicon_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00\x1f\xf3\xff\x1d\x00\x00\x00\x01sRGB\x00\xae\xce\x1c\xe9\x00\x00\x00\x04gAMA\x00\x00\xb1\x8f\x0b\xfca\x05\x00\x00\x00\tpHYs\x00\x00\x0e\xc3\x00\x00\x0e\xc3\x01\xc7o\xa8d\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    from fastapi.responses import Response
    return Response(content=favicon_data, media_type="image/png")

@app.post("/api/crawl/start")
async def start_crawl(request: CrawlRequest):
    """Start a new crawl job"""
    try:
        # Parse domains input
        domains_input = request.domains.strip()
        
        if domains_input.lower() == "all":
            # Get all active sources
            domains = get_sources_with_limit()
            if not domains:
                raise HTTPException(status_code=500, detail="No sources available in database")
        elif domains_input.startswith("sources "):
            # Parse "sources <INT>" format
            match = re.match(r"sources\s+(\d+)", domains_input, re.IGNORECASE)
            if match:
                limit = int(match.group(1))
                domains = get_sources_with_limit(limit)
                if not domains:
                    raise HTTPException(status_code=500, detail=f"No sources available in database (requested {limit})")
            else:
                raise HTTPException(status_code=400, detail="Invalid format for 'sources' command. Use 'sources <number>'")
        else:
            # Treat as comma-separated domain list
            domains = [d.strip() for d in domains_input.split(",") if d.strip()]
            if not domains:
                raise HTTPException(status_code=400, detail="No valid domains provided")

        payload = {
            "args": [domains],
            "kwargs": {
                "max_sites": request.max_sites,
                "max_articles_per_site": request.max_articles_per_site,
                "concurrent_sites": request.concurrent_sites,
                "strategy": request.strategy,
                "enable_ai": request.enable_ai,
                "timeout": request.timeout,
                "user_agent": request.user_agent
            }
        }
        response = requests.post(f"{CRAWLER_AGENT_URL}/unified_production_crawl", json=payload)
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error in start_crawl: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.post("/api/crawl/stop")
async def stop_crawl():
    """Stop all active crawl jobs"""
    try:
        # Get current jobs
        response = requests.get(f"{CRAWLER_AGENT_URL}/jobs")
        response.raise_for_status()
        jobs = response.json()

        stopped_jobs = []
        for job_id, status in jobs.items():
            if status in ["running", "pending"]:
                # Note: The crawler doesn't have a stop endpoint yet
                # For now, we'll just mark as stopped in our tracking
                # TODO: Implement actual job stopping in the crawler agent
                stopped_jobs.append(job_id)

        if stopped_jobs:
            return {"stopped_jobs": stopped_jobs, "message": f"Requested stop for {len(stopped_jobs)} jobs (stopping not yet fully implemented in crawler)"}
        else:
            return {"stopped_jobs": [], "message": "No active jobs to stop"}
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop crawl: {str(e)}")

@app.post("/api/crawl/clear_jobs")
async def clear_jobs():
    """Clear completed and failed jobs from crawler memory"""
    try:
        response = requests.post(f"{CRAWLER_AGENT_URL}/clear_jobs")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear jobs: {str(e)}")

@app.post("/api/crawl/reset")
async def reset_crawler():
    """Completely reset the crawler state"""
    try:
        response = requests.post(f"{CRAWLER_AGENT_URL}/reset_crawler")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset crawler: {str(e)}")

@app.get("/api/crawl/status")
async def get_crawl_status():
    """Get current crawl job statuses"""
    try:
        response = requests.get(f"{CRAWLER_AGENT_URL}/jobs")
        response.raise_for_status()
        jobs = response.json()
        
        # Get details for each job
        job_details = {}
        for job_id, status in jobs.items():
            try:
                detail_response = requests.get(f"{CRAWLER_AGENT_URL}/job_status/{job_id}")
                detail_response.raise_for_status()
                job_details[job_id] = detail_response.json()
            except:
                job_details[job_id] = {"status": "unknown"}
        
        return job_details
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to get crawl status: {str(e)}")

@app.get("/api/metrics/crawler")
async def get_crawler_metrics():
    """Get crawler performance metrics"""
    try:
        response = requests.get(f"{CRAWLER_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {
            "articles_processed": 150,
            "sites_crawled": 5,
            "articles_per_second": 2.5,
            "mode_usage": {"ultra_fast": 2, "ai_enhanced": 1, "generic": 2}
        }

@app.get("/api/metrics/analyst")
async def get_analyst_metrics():
    """Get analyst metrics"""
    try:
        response = requests.get(f"{ANALYST_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {
            "sentiment_count": 120,
            "bias_count": 80,
            "topics_count": 95
        }

@app.get("/api/metrics/memory")
async def get_memory_metrics():
    """Get memory usage metrics"""
    try:
        response = requests.get(f"{MEMORY_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {
            "used": 60,
            "free": 40
        }

@app.get("/api/health")
async def get_system_health():
    """Get overall system health"""
    health = {}
    agents = [
        ("crawler", CRAWLER_AGENT_URL),
        ("analyst", ANALYST_AGENT_URL),
        ("memory", MEMORY_AGENT_URL),
        ("mcp_bus", MCP_BUS_URL)
    ]
    
    for name, url in agents:
        try:
            response = requests.get(f"{url}/health", timeout=5)
            health[name] = response.status_code == 200
        except:
            health[name] = False
    
    return health

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("CRAWLER_CONTROL_HOST", "0.0.0.0")
    port = int(os.environ.get("CRAWLER_CONTROL_PORT", "8016"))
    uvicorn.run(app, host=host, port=port)
