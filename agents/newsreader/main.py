"""
NewsReader Agent - Main FastAPI Application

This is the main entry point for the NewsReader agent, providing RESTful APIs
for news content processing using vision-language models.

Features:
- FastAPI web server with MCP bus integration
- News URL processing endpoints
- Health checks and monitoring
- Production-ready error handling and logging

Endpoints:
- POST /process_url: Process a news article URL
- GET /health: Health check endpoint
- GET /stats: Processing statistics
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

from common.observability import get_logger
from .newsreader_engine import NewsReaderEngine, NewsReaderConfig, ProcessingMode
from .tools import process_article_content, health_check, memory_monitor, cleanup_temp_files

# MCP Bus integration
try:
    from common.mcp_bus_client import MCPBusClient
    MCP_AVAILABLE = True
except ImportError:
    MCPBusClient = None
    MCP_AVAILABLE = False

logger = get_logger(__name__)

# Global engine instance
engine: Optional[NewsReaderEngine] = None

# Request/Response Models
class ProcessURLRequest(BaseModel):
    """Request model for URL processing."""
    url: HttpUrl = Field(..., description="News article URL to process")
    mode: ProcessingMode = Field(default=ProcessingMode.COMPREHENSIVE, description="Processing mode")
    custom_prompt: Optional[str] = Field(None, description="Custom analysis prompt")
    save_screenshot: bool = Field(default=False, description="Whether to save screenshot")

class ProcessURLResponse(BaseModel):
    """Response model for URL processing."""
    success: bool = Field(..., description="Processing success status")
    url: str = Field(..., description="Processed URL")
    content_type: str = Field(..., description="Content type detected")
    extracted_text: str = Field(..., description="Extracted text content")
    visual_description: str = Field(..., description="Visual analysis description")
    confidence_score: float = Field(..., description="Confidence score (0.0-1.0)")
    processing_time: float = Field(..., description="Processing time in seconds")
    timestamp: float = Field(..., description="Processing timestamp")
    processing_mode: str = Field(..., description="Processing mode used")

class HealthResponse(BaseModel):
    """Response model for health checks."""
    timestamp: float = Field(..., description="Health check timestamp")
    overall_status: str = Field(..., description="Overall health status")
    components: Dict[str, Any] = Field(..., description="Component health status")
    issues: list[str] = Field(..., description="List of issues found")

class StatsResponse(BaseModel):
    """Response model for statistics."""
    total_processed: int = Field(..., description="Total URLs processed")
    success_rate: float = Field(..., description="Success rate (0.0-1.0)")
    average_processing_time: float = Field(..., description="Average processing time")
    memory_stats: Optional[Dict[str, Any]] = Field(None, description="Current memory statistics")
    uptime: float = Field(..., description="Service uptime in seconds")

# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    global engine

    # Startup
    logger.info("🚀 Starting NewsReader Agent...")

    try:
        # Initialize engine
        config = NewsReaderConfig()
        engine = NewsReaderEngine(config)

        # Start memory monitoring
        memory_monitor.start_monitoring()

        # Register with MCP Bus if available
        if MCP_AVAILABLE:
            await register_with_mcp_bus()

        logger.info("✅ NewsReader Agent started successfully")

        yield

    except Exception as e:
        logger.error(f"❌ Failed to start NewsReader Agent: {e}")
        raise
    finally:
        # Shutdown
        logger.info("🛑 Shutting down NewsReader Agent...")

        # Stop memory monitoring
        memory_monitor.stop_monitoring()

        # Cleanup engine
        if engine:
            engine._cleanup_gpu_memory()

        # Cleanup temp files
        cleanup_temp_files()

        logger.info("✅ NewsReader Agent shutdown complete")

async def register_with_mcp_bus():
    """Register agent with MCP Bus."""
    if not MCP_AVAILABLE:
        logger.warning("MCP Bus client not available - skipping registration")
        return

    try:
        mcp_bus_url = os.getenv("MCP_BUS_URL", "http://localhost:8000")
        client = MCPBusClient(mcp_bus_url)

        agent_info = {
            "name": "newsreader",
            "description": "News content processing with vision-language models",
            "version": "2.0.0",
            "capabilities": ["url_processing", "content_extraction", "visual_analysis"],
            "endpoints": {
                "process_url": "/process_url",
                "health": "/health",
                "stats": "/stats"
            }
        }

        await client.register_agent(agent_info)
        logger.info("✅ Registered with MCP Bus")

    except Exception as e:
        logger.error(f"❌ MCP Bus registration failed: {e}")

# Create FastAPI app
app = FastAPI(
    title="NewsReader Agent",
    description="Multi-modal news content processing using vision-language models",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global startup time
startup_time = time.time()

@app.get("/")
async def root():
    """Root endpoint with basic information."""
    return {
        "name": "NewsReader Agent",
        "version": "2.0.0",
        "description": "News content processing with LLaVA vision-language models",
        "status": "running"
    }

@app.post("/process_url", response_model=ProcessURLResponse)
async def process_url_endpoint(
    request: ProcessURLRequest,
    background_tasks: BackgroundTasks
):
    """
    Process a news article URL for content extraction.

    This endpoint captures a screenshot of the webpage and uses LLaVA
    vision-language model to extract and analyze the news content.
    """
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="NewsReader engine not initialized")

    try:
        logger.info(f"📨 Processing URL request: {request.url}")

        # Process the URL
        screenshot_path = f"temp/screenshot_{int(time.time())}.png" if request.save_screenshot else None

        result = await process_article_content(
            str(request.url),
            engine,
            request.mode,
            screenshot_path,
            request.custom_prompt
        )

        # Schedule cleanup if screenshot was saved
        if request.save_screenshot and screenshot_path:
            background_tasks.add_task(cleanup_temp_files)

        # Validate result
        if not result.get("success", False):
            logger.warning(f"Processing failed for URL: {request.url}")
            # Don't raise exception for processing failures, just return the result

        response = ProcessURLResponse(**result)
        logger.info(f"✅ URL processing completed: {result.get('processing_time', 0):.2f}s")
        return response

    except ValueError as e:
        logger.error(f"❌ Invalid request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """Health check endpoint for monitoring and load balancers."""
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="NewsReader engine not initialized")

    try:
        health_result = await health_check(engine)
        return HealthResponse(**health_result)
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/stats", response_model=StatsResponse)
async def stats_endpoint():
    """Get processing statistics and performance metrics."""
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="NewsReader engine not initialized")

    try:
        uptime = time.time() - startup_time

        stats = StatsResponse(
            total_processed=engine.processing_stats['total_processed'],
            success_rate=engine.processing_stats['success_rate'],
            average_processing_time=engine.processing_stats['average_processing_time'],
            memory_stats=memory_monitor.get_memory_stats()[-1] if memory_monitor.memory_stats else None,
            uptime=uptime
        )

        return stats

    except Exception as e:
        logger.error(f"❌ Stats retrieval error: {e}")
        raise HTTPException(status_code=500, detail=f"Stats retrieval failed: {str(e)}")

@app.get("/capabilities")
async def capabilities_endpoint():
    """Get agent capabilities and supported features."""
    return {
        "name": "NewsReader Agent",
        "version": "2.0.0",
        "capabilities": [
            "url_processing",
            "content_extraction",
            "visual_analysis",
            "screenshot_capture",
            "llava_integration"
        ],
        "supported_modes": ["fast", "comprehensive"],
        "supported_formats": ["json", "text", "markdown"],
        "max_url_length": 2048,
        "rate_limits": {
            "requests_per_minute": 10,
            "concurrent_requests": 3
        }
    }

# Error handlers
@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle internal server errors."""
    logger.error(f"500 Internal Server Error: {exc}")
    return {
        "error": "Internal server error",
        "detail": str(exc) if os.getenv("DEBUG", "").lower() == "true" else "An unexpected error occurred"
    }

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 not found errors."""
    return {
        "error": "Not found",
        "detail": f"Endpoint {request.url.path} not found"
    }

if __name__ == "__main__":
    import uvicorn

    # Run with uvicorn for development
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8002")),
        reload=True,
        log_level="info"
    )