"""
Main file for the Archive Agent.
"""
# main.py for Archive Agent

import os
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.archive.archive_manager import ArchiveManager
from common.observability import get_logger

# Import metrics library
from common.metrics import JustNewsMetrics

# Configure logging
logger = get_logger(__name__)

ready = False

# Environment variables
ARCHIVE_AGENT_PORT = int(os.environ.get("ARCHIVE_AGENT_PORT", 8012))
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

# Initialize archive manager
archive_manager = ArchiveManager({
    "type": "local",
    "local_path": "./archive_storage",
    "kg_storage_path": "./kg_storage"
})

# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Archive agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="archive",
            agent_address=f"http://localhost:{ARCHIVE_AGENT_PORT}",
            tools=["archive_articles", "retrieve_article", "search_archive", "get_archive_stats"],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield

    logger.info("Archive agent is shutting down.")

# Initialize FastAPI with the lifespan context manager
app = FastAPI(title="Archive Agent", lifespan=lifespan)

# Initialize metrics
metrics = JustNewsMetrics("archive")

# Register common shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for archive")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for archive")

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
    args: list
    kwargs: dict

class ArticleData(BaseModel):
    url: str
    url_hash: str
    domain: str
    title: str
    content: str
    extraction_method: str = "generic_dom"
    status: str = "success"
    crawl_mode: str = "generic_site"
    canonical: str = ""
    paywall_flag: bool = False
    confidence: float = 0.8
    publisher_meta: dict = {}
    news_score: float = 0.7
    timestamp: str = ""

class CrawlerResults(BaseModel):
    multi_site_crawl: bool = False
    sites_crawled: int = 0
    total_articles: int = 0
    processing_time_seconds: float = 0.0
    articles_per_second: float = 0.0
    articles: list[ArticleData] = []

@app.post("/archive_articles")
async def archive_articles(call: ToolCall):
    """Archive articles from crawler results with Knowledge Graph integration"""
    try:
        from datetime import datetime

        kwargs = call.kwargs or {}

        # Convert kwargs to CrawlerResults format
        crawler_results = {
            "multi_site_crawl": kwargs.get("multi_site_crawl", False),
            "sites_crawled": kwargs.get("sites_crawled", 0),
            "total_articles": kwargs.get("total_articles", 0),
            "processing_time_seconds": kwargs.get("processing_time_seconds", 0.0),
            "articles_per_second": kwargs.get("articles_per_second", 0.0),
            "articles": kwargs.get("articles", [])
        }

        if not crawler_results["articles"]:
            raise HTTPException(status_code=400, detail="No articles provided for archiving")

        # Run async archive operation directly (no asyncio.run needed)
        archive_summary = await archive_manager.archive_from_crawler(crawler_results)

        logger.info(f"Archived {len(crawler_results['articles'])} articles")
        return {"status": "success", "data": archive_summary}
    except Exception as e:
        logger.error(f"Error archiving articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/retrieve_article")
async def retrieve_article(call: ToolCall):
    """Retrieve archived article by storage key"""
    try:
        kwargs = call.kwargs or {}
        storage_key = kwargs.get("storage_key")

        if not storage_key:
            raise HTTPException(status_code=400, detail="storage_key is required")

        # Run async retrieval operation directly (no asyncio.run needed)
        article_data = await archive_manager.storage_manager.retrieve_article(storage_key)

        if article_data is None:
            raise HTTPException(status_code=404, detail=f"Article not found: {storage_key}")

        logger.info(f"Retrieved article: {storage_key}")
        return {"status": "success", "data": article_data}
    except Exception as e:
        logger.error(f"Error retrieving article: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search_archive")
async def search_archive(call: ToolCall):
    """Search archived articles by metadata"""
    try:
        kwargs = call.kwargs or {}
        query = kwargs.get("query", "")
        filters = kwargs.get("filters", {})

        if not query:
            raise HTTPException(status_code=400, detail="query is required")

        # Run async search operation directly (no asyncio.run needed)
        storage_keys = await archive_manager.metadata_index.search_articles(query, filters)

        logger.info(f"Search query '{query}' returned {len(storage_keys)} results")
        return {"status": "success", "data": {"query": query, "results": storage_keys, "count": len(storage_keys)}}
    except Exception as e:
        logger.error(f"Error searching archive: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_archive_stats")
def get_archive_stats(call: ToolCall):
    """Get comprehensive archive statistics"""
    try:
        import os
        from pathlib import Path

        # Get storage statistics
        storage_path = Path("./archive_storage")
        total_files = 0
        total_size = 0

        if storage_path.exists():
            for file_path in storage_path.rglob("*"):
                if file_path.is_file():
                    total_files += 1
                    total_size += file_path.stat().st_size

        # Get Knowledge Graph statistics
        kg_stats = archive_manager.kg_manager.get_statistics() if hasattr(archive_manager.kg_manager, 'get_statistics') else {}

        stats = {
            "storage_type": archive_manager.storage_config.get("type", "local"),
            "total_archived_articles": total_files,
            "total_storage_size_bytes": total_size,
            "total_storage_size_mb": round(total_size / (1024 * 1024), 2),
            "storage_path": str(storage_path.absolute()),
            "knowledge_graph_enabled": True,
            "knowledge_graph_stats": kg_stats,
            "archive_manager_initialized": True,
            "phase3_integration": True
        }

        logger.info(f"Retrieved archive statistics: {total_files} articles, {stats['total_storage_size_mb']} MB")
        return {"status": "success", "data": stats}
    except Exception as e:
        logger.error(f"Error getting archive stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/store_single_article")
async def store_single_article(call: ToolCall):
    """Store a single article with complete metadata"""
    try:
        from datetime import datetime

        kwargs = call.kwargs or {}

        # Validate required fields
        required_fields = ["url", "title", "content", "domain"]
        for field in required_fields:
            if field not in kwargs:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        # Prepare article data
        article_data = {
            "url": kwargs["url"],
            "url_hash": kwargs.get("url_hash", ""),
            "domain": kwargs["domain"],
            "title": kwargs["title"],
            "content": kwargs["content"],
            "extraction_method": kwargs.get("extraction_method", "generic_dom"),
            "status": kwargs.get("status", "success"),
            "crawl_mode": kwargs.get("crawl_mode", "generic_site"),
            "canonical": kwargs.get("canonical", kwargs["url"]),
            "paywall_flag": kwargs.get("paywall_flag", False),
            "confidence": kwargs.get("confidence", 0.8),
            "publisher_meta": kwargs.get("publisher_meta", {}),
            "news_score": kwargs.get("news_score", 0.7),
            "timestamp": kwargs.get("timestamp", datetime.now().isoformat())
        }

        # Run async storage operation directly (no asyncio.run needed)
        storage_key = await archive_manager.storage_manager.store_article(article_data)

        logger.info(f"Stored single article: {kwargs['title'][:50]}...")
        return {"status": "success", "data": {"storage_key": storage_key, "article_title": kwargs["title"]}}
    except Exception as e:
        logger.error(f"Error storing single article: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=ARCHIVE_AGENT_PORT)
