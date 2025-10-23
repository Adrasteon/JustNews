"""
Main file for the Scout Agent.
"""
# main.py for Scout Agent

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Import security utilities
from agents.scout.security_utils import log_security_event, rate_limit, validate_url
from common.observability import get_logger
from common.metrics import JustNewsMetrics

# Configure logging

logger = get_logger(__name__)

ready = False

# Environment variables
SCOUT_AGENT_PORT = int(os.environ.get("SCOUT_AGENT_PORT", 8002))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Security configuration
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")

class MCPBusClient:
    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list[str]):
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            # Use shorter timeout to prevent hanging
            response = requests.post(f"{self.base_url}/register", json=registration_data, timeout=(1, 2))
            response.raise_for_status()
            logger.info(f"Successfully registered {agent_name} with MCP Bus.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register {agent_name} with MCP Bus: {e}")
            raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Scout agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        # Try to register with MCP Bus with shorter timeout
        mcp_bus_client.register_agent(
            agent_name="scout",
            agent_address=f"http://localhost:{SCOUT_AGENT_PORT}",
            tools=[
                "discover_sources", "crawl_url", "deep_crawl_site", "enhanced_deep_crawl_site",
                "intelligent_source_discovery", "intelligent_content_crawl",
                "intelligent_batch_analysis", "enhanced_newsreader_crawl",
                "production_crawl_ultra_fast", "get_production_crawler_info",
                "production_crawl_dynamic", "analyze_sentiment", "detect_bias"
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield
    logger.info("Scout agent is shutting down.")

app = FastAPI(lifespan=lifespan, title="Scout Agent", description="Secure web crawling and content analysis agent")

# Initialize metrics
metrics = JustNewsMetrics("scout")

# Security middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Metrics middleware (must be added after security middleware)
app.middleware("http")(metrics.request_middleware)

# Request middleware for rate limiting
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Security middleware for request validation and rate limiting."""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting per IP
    if not rate_limit(f"request_{client_ip}"):
        log_security_event('rate_limit_exceeded', {
            'ip': client_ip,
            'path': request.url.path,
            'method': request.method
        })
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": 60}
        )

    # Log suspicious requests
    user_agent = request.headers.get("user-agent", "")
    if not user_agent or len(user_agent) < 10:
        log_security_event('suspicious_request', {
            'ip': client_ip,
            'path': request.url.path,
            'user_agent': user_agent[:100]
        })

    response = await call_next(request)
    return response

# Register shutdown endpoint if available
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for scout")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for scout")

class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]

@app.post("/discover_sources")
def discover_sources(call: ToolCall):
    try:
        from agents.scout.tools import discover_sources
        logger.info(f"Calling discover_sources with args: {call.args} and kwargs: {call.kwargs}")
        return discover_sources(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in discover_sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/crawl_url")
def crawl_url(call: ToolCall):
    try:
        from agents.scout.tools import crawl_url
        logger.info(f"Calling crawl_url with args: {call.args} and kwargs: {call.kwargs}")

        # Validate URL if provided
        url = call.kwargs.get("url") or (call.args[0] if call.args else None)
        if url and not validate_url(url):
            log_security_event('url_validation_failed', {
                'url': url[:100],
                'endpoint': '/crawl_url'
            })
            raise HTTPException(status_code=400, detail="Invalid or unsafe URL")

        return crawl_url(*call.args, **call.kwargs)
    except ValueError as e:
        logger.warning(f"Validation error in crawl_url: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred in crawl_url: {e}")
        log_security_event('endpoint_error', {
            'endpoint': '/crawl_url',
            'error': str(e)
        })
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/deep_crawl_site")
def deep_crawl_site(call: ToolCall):
    try:
        from agents.scout.tools import deep_crawl_site
        logger.info(f"Calling deep_crawl_site with args: {call.args} and kwargs: {call.kwargs}")
        return deep_crawl_site(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in deep_crawl_site: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/enhanced_deep_crawl_site")
async def enhanced_deep_crawl_site_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import enhanced_deep_crawl_site
        logger.info(f"Calling enhanced_deep_crawl_site with args: {call.args} and kwargs: {call.kwargs}")

        # Validate URL if provided
        url = call.kwargs.get("url") or (call.args[0] if call.args else None)
        if url and not validate_url(url):
            log_security_event('url_validation_failed', {
                'url': url[:100],
                'endpoint': '/enhanced_deep_crawl_site'
            })
            raise HTTPException(status_code=400, detail="Invalid or unsafe URL")

        return await enhanced_deep_crawl_site(*call.args, **call.kwargs)
    except ValueError as e:
        logger.warning(f"Validation error in enhanced_deep_crawl_site: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred in enhanced_deep_crawl_site: {e}")
        log_security_event('endpoint_error', {
            'endpoint': '/enhanced_deep_crawl_site',
            'error': str(e)
        })
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/intelligent_source_discovery")
def intelligent_source_discovery_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import intelligent_source_discovery
        logger.info(f"Calling intelligent_source_discovery with args: {call.args} and kwargs: {call.kwargs}")
        return intelligent_source_discovery(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in intelligent_source_discovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/intelligent_content_crawl")
def intelligent_content_crawl_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import intelligent_content_crawl
        logger.info(f"Calling intelligent_content_crawl with args: {call.args} and kwargs: {call.kwargs}")
        return intelligent_content_crawl(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in intelligent_content_crawl: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/intelligent_batch_analysis")
def intelligent_batch_analysis_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import intelligent_batch_analysis
        logger.info(f"Calling intelligent_batch_analysis with args: {call.args} and kwargs: {call.kwargs}")
        return intelligent_batch_analysis(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in intelligent_batch_analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/enhanced_newsreader_crawl")
def enhanced_newsreader_crawl_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import enhanced_newsreader_crawl
        logger.info(f"Calling enhanced_newsreader_crawl with args: {call.args} and kwargs: {call.kwargs}")
        return enhanced_newsreader_crawl(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in enhanced_newsreader_crawl: {e}")
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
    from fastapi.responses import Response
    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")

@app.post("/log_feedback")
def log_feedback(call: ToolCall):
    try:
        feedback_data = {
            "timestamp": datetime.now().isoformat(),
            "feedback": call.kwargs.get("feedback")
        }
        logger.info(f"Logging feedback: {feedback_data}")
        return feedback_data
    except Exception as e:
        logger.error(f"An error occurred while logging feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze_sentiment")
def analyze_sentiment_endpoint(call: ToolCall):
    """Analyze sentiment in provided text content."""
    try:
        from agents.scout.gpu_scout_engine_v2 import NextGenGPUScoutEngine
        text = call.kwargs.get("text")
        if not text:
            raise HTTPException(status_code=400, detail="Text parameter required")

        # Use cached engine instance to avoid GPU memory issues
        if not hasattr(analyze_sentiment_endpoint, '_engine'):
            analyze_sentiment_endpoint._engine = NextGenGPUScoutEngine(enable_training=False)

        engine = analyze_sentiment_endpoint._engine
        result = engine.analyze_sentiment(text)
        return result
    except Exception as e:
        logger.error(f"An error occurred in analyze_sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/detect_bias")
def detect_bias_endpoint(call: ToolCall):
    """Detect bias in provided text content."""
    try:
        from agents.scout.gpu_scout_engine_v2 import NextGenGPUScoutEngine
        text = call.kwargs.get("text")
        if not text:
            raise HTTPException(status_code=400, detail="Text parameter required")

        # Use cached engine instance to avoid GPU memory issues
        if not hasattr(detect_bias_endpoint, '_engine'):
            detect_bias_endpoint._engine = NextGenGPUScoutEngine(enable_training=False)

        engine = detect_bias_endpoint._engine
        result = engine.detect_bias(text)
        return result
    except Exception as e:
        logger.error(f"An error occurred in detect_bias: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# PRODUCTION CRAWLER ENDPOINTS
# =============================================================================


@app.post("/production_crawl_ai_enhanced")
async def production_crawl_ai_enhanced_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import production_crawl_ai_enhanced
        logger.info(f"Calling production_crawl_ai_enhanced with args: {call.args} and kwargs: {call.kwargs}")

        # Validate site parameter
        site = call.kwargs.get("site") or (call.args[0] if call.args else None)
        if not site or not isinstance(site, str):
            log_security_event('invalid_site', {
                'endpoint': '/production_crawl_ai_enhanced',
                'site': str(site)[:50]
            })
            raise HTTPException(status_code=400, detail="Invalid site identifier")

        return await production_crawl_ai_enhanced(*call.args, **call.kwargs)
    except ValueError as e:
        logger.warning(f"Validation error in production_crawl_ai_enhanced: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred in production_crawl_ai_enhanced: {e}")
        log_security_event('endpoint_error', {
            'endpoint': '/production_crawl_ai_enhanced',
            'error': str(e)
        })
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/production_crawl_ultra_fast")
async def production_crawl_ultra_fast_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import production_crawl_ultra_fast
        logger.info(f"Calling production_crawl_ultra_fast with args: {call.args} and kwargs: {call.kwargs}")

        # Validate site parameter
        site = call.kwargs.get("site") or (call.args[0] if call.args else None)
        if not site or not isinstance(site, str):
            log_security_event('invalid_site', {
                'endpoint': '/production_crawl_ultra_fast',
                'site': str(site)[:50]
            })
            raise HTTPException(status_code=400, detail="Invalid site identifier")

        return await production_crawl_ultra_fast(*call.args, **call.kwargs)
    except ValueError as e:
        logger.warning(f"Validation error in production_crawl_ultra_fast: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"An error occurred in production_crawl_ultra_fast: {e}")
        log_security_event('endpoint_error', {
            'endpoint': '/production_crawl_ultra_fast',
            'error': str(e)
        })
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/get_production_crawler_info")
def get_production_crawler_info_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import get_production_crawler_info
        logger.info(f"Calling get_production_crawler_info with args: {call.args} and kwargs: {call.kwargs}")
        return get_production_crawler_info(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in get_production_crawler_info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/production_crawl_dynamic")
async def production_crawl_dynamic_endpoint(call: ToolCall):
    try:
        from agents.scout.tools import production_crawl_dynamic
        logger.info(f"Calling production_crawl_dynamic with args: {call.args} and kwargs: {call.kwargs}")
        # Expect kwargs: domains (list[str]|None), articles_per_site, concurrent_sites, max_total_articles
        return await production_crawl_dynamic(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in production_crawl_dynamic: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# SERVER STARTUP
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Scout Agent on port {SCOUT_AGENT_PORT}")
    uvicorn.run(
        "agents.scout.main:app",
        host="0.0.0.0",
        port=SCOUT_AGENT_PORT,
        reload=False,
        log_level="info"
    )
