"""
Main file for the Memory Agent.
"""
import os
from typing import Any
from contextlib import asynccontextmanager

import requests

from common.observability import get_logger
from common.metrics import JustNewsMetrics

try:
    # Optional import for Hugging Face hub login and snapshot_download
    import huggingface_hub
except Exception:
    huggingface_hub = None

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

# Import database utilities
from agents.common.database import close_connection_pool, initialize_connection_pool
from agents.common.database import execute_query
from agents.common.database import get_db_connection as get_pooled_connection
from agents.memory.tools import (
    get_all_article_ids,
    get_embedding_model,
    log_training_example,
    save_article,
    vector_search_articles_local,
)

# Configure centralized logging
logger = get_logger(__name__)

# Readiness flag
ready = False

# Shared pre-warmed embedding model (initialized at startup)
embedding_model = None

# Async storage queue and background worker
storage_queue: "asyncio.Queue[dict]" = None
storage_executor: ThreadPoolExecutor = None

# Environment variables
POSTGRES_HOST = os.environ.get("POSTGRES_HOST")
POSTGRES_DB = os.environ.get("POSTGRES_DB")
POSTGRES_USER = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
MEMORY_AGENT_PORT = int(os.environ.get("MEMORY_AGENT_PORT", 8007))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Pydantic models
class Article(BaseModel):
    content: str
    metadata: dict

    class Config:
        arbitrary_types_allowed = True

class TrainingExample(BaseModel):
    task: str
    input: dict
    output: dict
    critique: str

    model_config = ConfigDict(arbitrary_types_allowed=True)

class VectorSearch(BaseModel):
    query: str
    top_k: int = 5

    model_config = ConfigDict(arbitrary_types_allowed=True)

class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)

import time

class MCPBusClient:
    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list):
        registration_data = {
            "name": agent_name,
            "address": agent_address,
            "tools": tools,
        }
        
        max_retries = 5
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                response = requests.post(f"{self.base_url}/register", json=registration_data, timeout=(3, 10))
                response.raise_for_status()
                logger.info(f"Successfully registered {agent_name} with MCP Bus.")
                return
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to register {agent_name} with MCP Bus: {e}")
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor ** attempt
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Failed to register {agent_name} with MCP Bus after {max_retries} attempts.")
                    raise

# Use connection pooling for database connections
def get_db_connection():
    """Establishes a connection to the PostgreSQL database with pooling."""
    try:
        # Use the new connection pooling system
        return get_pooled_connection()
    except Exception as e:
        logger.error(f"Could not connect to PostgreSQL database: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")


async def _storage_consumer():
    """Background consumer to process storage tasks from the queue."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            task = await storage_queue.get()
            # task is dict with content and metadata
            # Run save_article in thread pool to avoid blocking event loop
            # Pass pre-warmed embedding_model to avoid repeated loads
            await loop.run_in_executor(
                storage_executor,
                lambda: save_article(task.get('content'), task.get('metadata'), embedding_model=embedding_model),
            )
            try:
                storage_queue.task_done()
            except Exception:
                pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in storage consumer: {e}")
            try:
                storage_queue.task_done()
            except Exception:
                pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown events for the FastAPI application."""
    logger.info("Memory agent is starting up.")
    # Initialize database connection pool
    try:
        initialize_connection_pool()
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database connection pool: {e}")
        raise
    # Register agent with MCP Bus
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="memory",
            agent_address=f"http://localhost:{MEMORY_AGENT_PORT}",
            tools=[
                "save_article",
                "get_article",
                "get_all_article_ids",
                "vector_search_articles",
                "log_training_example",
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    # Mark ready after startup and optional registration
    global ready
    ready = True
    # Initialize and pre-warm embedding model once
    global embedding_model
    # If operator provided HF token or cache path, configure environment for huggingface_hub
    hf_token = os.environ.get("HF_HUB_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    hf_cache = os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if hf_cache:
        # Prefer explicit HF_HOME to guide huggingface_hub cache location
        os.environ["HF_HOME"] = hf_cache
        logger.info(f"Set HF_HOME to {hf_cache} for model caching")
    if hf_token and huggingface_hub is not None:
        try:
            # login() sets token for subsequent hub downloads
            huggingface_hub.login(token=hf_token)
            logger.info("Authenticated with Hugging Face hub using HF_HUB_TOKEN")
        except Exception as e:
            logger.warning(f"Could not login to Hugging Face hub: {e}")
    elif hf_token and huggingface_hub is None:
        logger.warning("HF_HUB_TOKEN provided but huggingface_hub package is not available")
    try:
        embedding_model = get_embedding_model()
        logger.info("Pre-warmed embedding model successfully.")
    except Exception as e:
        logger.warning(f"Could not pre-warm embedding model at startup: {e}")
    # Initialize async queue and background worker
    global storage_queue, storage_executor
    storage_queue = asyncio.Queue()
    storage_executor = ThreadPoolExecutor(max_workers=2)

    # Start background consumer
    app.state.storage_consumer = asyncio.create_task(_storage_consumer())
    yield
    logger.info("Memory agent is shutting down.")
    # Shutdown background consumer
    try:
        # Cancel consumer task and drain remaining items
        app.state.storage_consumer.cancel()
    except Exception:
        pass
    # Drain the queue (wait briefly for pending tasks to complete)
    try:
        async def _drain():
            # Allow a short grace period for in-flight items
            timeout = 10
            start = asyncio.get_event_loop().time()
            while not storage_queue.empty() and (asyncio.get_event_loop().time() - start) < timeout:
                logger.info(f"Draining storage queue; remaining={storage_queue.qsize()}")
                await asyncio.sleep(0.5)

        # We're already in an async context here; await the drain coroutine
        await _drain()
    except Exception:
        pass
    try:
        storage_executor.shutdown(wait=False)
    except Exception:
        pass
    # Close database connection pool
    try:
        close_connection_pool()
        logger.info("Database connection pool closed")
    except Exception as e:
        logger.error(f"Error closing database connection pool: {e}")

app = FastAPI(lifespan=lifespan)

# Initialize metrics
metrics = JustNewsMetrics("memory")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)

# Register common shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for memory")

# Register reload endpoint and handler for runtime reloads (embedding etc.)
try:
    from agents.common.reload import register_reload_endpoint, register_reload_handler

    def _reload_embedding_model():
        """Reload the embedding model from ModelStore / cache and return a small status."""
        global embedding_model
        try:
            embedding_model = get_embedding_model()
            return {"reloaded": True}
        except Exception as e:
            # preserve previous model on failure
            return {"reloaded": False, "error": str(e)}

    register_reload_handler('embedding_model', _reload_embedding_model)
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for memory")

from fastapi import Request

@app.get("/health")
@app.post("/health")
async def health(request: Request):
    """Health check endpoint that accepts optional body."""
    return {"status": "ok"}


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint"""
    from fastapi.responses import Response
    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")

@app.get("/ready")
def ready_endpoint():
    """Readiness endpoint for startup gating."""
    return {"ready": ready}

@app.post("/save_article")
def save_article_endpoint(request: dict):
    """Saves an article to the database. Handles both direct calls and MCP Bus format."""
    try:
        # Handle MCP Bus format: {"args": [...], "kwargs": {...}}
        if "args" in request and "kwargs" in request:
            if len(request["args"]) > 0:
                article_data = request["args"][0]
            else:
                article_data = request["kwargs"]
        else:
            # Direct call format
            article_data = request

        # Create Article object from the data
        article = Article(**article_data)
        # Use pre-warmed embedding_model if available to avoid re-loading the model
        return save_article(article.content, article.metadata, embedding_model=embedding_model)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error saving article: {str(e)}")

from fastapi import Request

@app.post("/get_article")
async def get_article_endpoint(request: Request):
    """
    Retrieves an article from the database. This endpoint is designed
    to be called from the MCP Bus and manually parses the JSON payload
    to avoid Pydantic deserialization issues.
    """
    try:
        payload = await request.json()
        retrieval_id = None
        
        # The payload from the bus is a dict: {"args": [], "kwargs": {...}}
        if "kwargs" in payload and "article_id" in payload["kwargs"]:
            retrieval_id = int(payload["kwargs"]["article_id"])

        if retrieval_id is None:
            raise HTTPException(status_code=400, detail="article_id must be provided in the 'kwargs' of the tool call payload")

        from agents.common.database import execute_query_single
        article = execute_query_single("SELECT * FROM articles WHERE id = %s", (retrieval_id,))
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        return article
    except HTTPException:
        raise  # Re-raise known HTTP exceptions
    except Exception as e:
        logger.error(f"Error retrieving article: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving article: {str(e)}")

@app.post("/get_all_article_ids")
async def get_all_article_ids_endpoint(request: Request):
    """Retrieves all article IDs from the database."""
    logger.info("Received request for get_all_article_ids_endpoint")
    from agents.memory.tools import get_all_article_ids
    result = get_all_article_ids()
    logger.info(f"Returning result from get_all_article_ids_endpoint: {result}")
    return result

@app.post("/vector_search_articles")
def vector_search_articles_endpoint(request: dict):
    """Performs a vector search for articles. Handles both direct calls and MCP Bus format."""
    try:
        # Handle MCP Bus format: {"args": [...], "kwargs": {...}}
        if "args" in request and "kwargs" in request:
            if len(request["args"]) > 0:
                search_data = request["args"][0]
            else:
                search_data = request["kwargs"]
        else:
            # Direct call format
            search_data = request

        # Create VectorSearch object from the data
        search = VectorSearch(**search_data)
        # Use local in-process search implementation to avoid making HTTP
        # requests to ourselves which can cause recursive blocking behavior.
        return vector_search_articles_local(search.query, search.top_k)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error searching articles: {str(e)}")

@app.post("/get_recent_articles")
def get_recent_articles_endpoint(request: dict):
    """Returns the most recent articles for synthesis/testing.

    Accepts both direct calls ({"limit": 10}) and MCP-style calls
    ({"args": [ {"limit": 10} ], "kwargs": {}}) or ({"args": [], "kwargs": {"limit": 10}}).
    Falls back to a default limit of 10.
    """
    try:
        # Normalize payload
        limit = 10
        if isinstance(request, dict) and "args" in request and "kwargs" in request:
            if request.get("args"):
                arg0 = request["args"][0]
                if isinstance(arg0, dict) and "limit" in arg0:
                    limit = int(arg0.get("limit", limit))
            if "limit" in request.get("kwargs", {}):
                limit = int(request["kwargs"].get("limit", limit))
        elif isinstance(request, dict):
            limit = int(request.get("limit", limit))

        # Fetch most recent articles by id (no created_at column guaranteed)
        rows = execute_query(
            "SELECT id, content, metadata FROM articles ORDER BY id DESC LIMIT %s",
            (limit,)
        ) or []
        # Ensure JSON-serializable metadata
        for r in rows:
            if isinstance(r.get("metadata"), str):
                # some drivers already return dict, but if str, try to parse json
                try:
                    import json as _json
                    r["metadata"] = _json.loads(r["metadata"])  # type: ignore[index]
                except Exception:
                    pass
        return {"articles": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving recent articles: {str(e)}")

@app.post("/log_training_example")
def log_training_example_endpoint(example: TrainingExample):
    """Logs a training example to the database."""
    return log_training_example(
        example.task, example.input, example.output, example.critique
    )

@app.post("/ingest_article")
def ingest_article_endpoint(request: dict):
    """Handles article ingestion with sources and article_source_map operations.
    
    This endpoint replaces the db_worker functionality, handling the transactional
    insertion of sources, article_source_map, and articles as expected by crawlers.
    """
    try:
        # Handle MCP Bus format: {"args": [...], "kwargs": {...}}
        if "args" in request and "kwargs" in request:
            kwargs = request["kwargs"]
        else:
            # Direct call format
            kwargs = request
            
        article_payload = kwargs.get("article_payload", {})
        statements = kwargs.get("statements", [])
        
        if not article_payload:
            raise HTTPException(status_code=400, detail="Missing article_payload")
            
        logger.info(f"Ingesting article: {article_payload.get('url')}")
        
        # Execute statements transactionally
        chosen_source_id = None
        try:
            # Use the database connection utilities
            from agents.common.database import execute_query_single
            
            for sql, params in statements:
                try:
                    # Execute each statement - the crawler builds the right SQL
                    if "RETURNING id" in sql.upper():
                        # For statements that return IDs (like source upsert)
                        result = execute_query_single(sql, tuple(params))
                        if result and 'id' in result:
                            chosen_source_id = result['id']
                    else:
                        # For regular inserts
                        execute_query(sql, tuple(params), fetch=False)
                except Exception as stmt_e:
                    # Handle duplicate key errors for sources gracefully
                    if "unique constraint" in str(stmt_e).lower() or "duplicate key" in str(stmt_e).lower():
                        logger.debug(f"Source already exists, skipping insert: {stmt_e}")
                        # Try to get the existing source ID
                        if "sources" in sql and "domain" in str(params):
                            domain = params[1] if len(params) > 1 else None
                            if domain:
                                existing_source = execute_query_single("SELECT id FROM sources WHERE domain = %s", (domain,))
                                if existing_source:
                                    chosen_source_id = existing_source['id']
                                    logger.debug(f"Using existing source ID: {chosen_source_id}")
                    else:
                        # Re-raise non-duplicate errors
                        raise stmt_e
                    
        except Exception as e:
            logger.error(f"Database transaction failed: {e}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
            
        # Now save the article content using the memory agent's save_article function
        try:
            content = article_payload.get("content", "")
            metadata = {
                "url": article_payload.get("url"),
                "title": article_payload.get("title"),
                "domain": article_payload.get("domain"),
                "publisher_meta": article_payload.get("publisher_meta", {}),
                "confidence": article_payload.get("confidence", 0.5),
                "paywall_flag": article_payload.get("paywall_flag", False),
                "extraction_metadata": article_payload.get("extraction_metadata", {}),
                "timestamp": article_payload.get("timestamp"),
                "url_hash": article_payload.get("url_hash"),
                "canonical": article_payload.get("canonical"),
            }
            
            if content:  # Only save if there's actual content
                save_result = save_article(content, metadata, embedding_model=embedding_model)
                if save_result.get("status") == "duplicate":
                    logger.info(f"Article already exists, skipping: {article_payload.get('url')}")
                    # Return success status for duplicates since ingestion was technically successful
                    resp = {"status": "ok", "url": article_payload.get('url'), "duplicate": True, "existing_id": save_result.get("article_id")}
                else:
                    logger.info(f"Article saved with ID: {save_result.get('article_id')}")
                    resp = {"status": "ok", "url": article_payload.get('url')}
            else:
                logger.warning(f"No content to save for article: {article_payload.get('url')}")
                resp = {"status": "ok", "url": article_payload.get('url'), "no_content": True}
            
        except Exception as e:
            logger.warning(f"Failed to save article content: {e}")
            # Don't fail the whole ingestion if content saving fails
            resp = {"status": "ok", "url": article_payload.get('url'), "content_save_error": str(e)}
        return resp
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion error: {str(e)}")

# Improved error handling and logging
@app.get("/get_article_count")
def get_article_count_endpoint():
    """Get total count of articles in database."""
    try:
        from agents.common.database import execute_query_single
        result = execute_query_single("SELECT COUNT(*) as count FROM articles")
        return {"count": result.get("count", 0) if result else 0}
    except Exception as e:
        logger.error(f"Error getting article count: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving article count: {str(e)}")

@app.post("/get_sources")
def get_sources_endpoint(request: dict):
    """Get list of sources from the database.
    
    Args:
        limit: Maximum number of sources to return (default: 10)
        
    Returns:
        List of source dictionaries with domain, name, etc.
    """
    try:
        # Handle MCP Bus format: {"args": [...], "kwargs": {...}}
        if "args" in request and "kwargs" in request:
            kwargs = request["kwargs"]
        else:
            # Direct call format
            kwargs = request
            
        limit = kwargs.get("limit", 10)
        
        from agents.common.database import execute_query
        sources = execute_query(
            "SELECT id, url, domain, name, description, country, language FROM sources ORDER BY id LIMIT %s", 
            (limit,)
        )
        
        return {"sources": sources}
        
    except Exception as e:
        logger.error(f"Error getting sources: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving sources: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    import os

    host = os.environ.get("MEMORY_HOST", "0.0.0.0")
    port = int(os.environ.get("MEMORY_PORT", 8007))

    logger.info(f"Starting Memory Agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port)