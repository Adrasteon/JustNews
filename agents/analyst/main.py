"""
Analyst Agent - Main FastAPI Application

This is the main entry point for the Analyst agent, providing RESTful APIs
for quantitative news content analysis including entity extraction, statistical
analysis, sentiment/bias detection, and trend analysis.

Features:
- FastAPI web server with MCP bus integration
- Comprehensive quantitative analysis endpoints
- GPU-accelerated sentiment and bias analysis
- Health checks and monitoring
- Production-ready error handling and logging

Endpoints:
- POST /identify_entities: Extract named entities from text
- POST /analyze_text_statistics: Comprehensive text statistical analysis
- POST /extract_key_metrics: Extract numerical and statistical metrics
- POST /analyze_content_trends: Analyze trends across multiple content pieces
- POST /analyze_sentiment: Sentiment analysis with GPU acceleration
- POST /detect_bias: Bias detection with GPU acceleration
- POST /analyze_sentiment_and_bias: Combined sentiment and bias analysis
- GET /health: Health check endpoint
- GET /stats: Processing statistics

All endpoints include security validation, error handling, and comprehensive logging.
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from common.observability import get_logger
from common.metrics import JustNewsMetrics
from common.version_utils import get_version

from .tools import (
    identify_entities,
    analyze_text_statistics,
    extract_key_metrics,
    analyze_content_trends,
    analyze_sentiment,
    detect_bias,
    analyze_sentiment_and_bias,
    health_check,
    validate_analysis_result,
    format_analysis_output
)

# MCP Bus integration
try:
    from common.mcp_bus_client import MCPBusClient
    MCP_AVAILABLE = True
except ImportError:
    MCPBusClient = None
    MCP_AVAILABLE = False

logger = get_logger(__name__)

# Environment variables
ANALYST_AGENT_PORT = int(os.environ.get("ANALYST_AGENT_PORT", 8004))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Request/Response Models
class AnalysisRequest(BaseModel):
    """Base request model for analysis operations."""
    text: str = Field(..., min_length=1, max_length=1000000, description="Text content to analyze")
    format_output: str = Field("json", description="Output format (json, text, markdown)")

class EntitiesRequest(AnalysisRequest):
    """Request model for entity extraction."""
    pass

class StatisticsRequest(AnalysisRequest):
    """Request model for text statistics analysis."""
    pass

class MetricsRequest(AnalysisRequest):
    """Request model for key metrics extraction."""
    url: Optional[str] = Field(None, description="Article URL for context")

class TrendsRequest(BaseModel):
    """Request model for content trends analysis."""
    texts: List[str] = Field(..., min_items=1, description="List of texts to analyze")
    urls: Optional[List[str]] = Field(None, description="Corresponding URLs for context")
    format_output: str = Field("json", description="Output format (json, text, markdown)")

class SentimentRequest(AnalysisRequest):
    """Request model for sentiment analysis."""
    pass

class BiasRequest(AnalysisRequest):
    """Request model for bias detection."""
    pass

class CombinedAnalysisRequest(AnalysisRequest):
    """Request model for combined sentiment and bias analysis."""
    pass

class AnalysisResponse(BaseModel):
    """Base response model for analysis operations."""
    success: bool = Field(..., description="Analysis success status")
    result: Dict[str, Any] = Field(..., description="Analysis result data")
    processing_time: float = Field(..., description="Processing time in seconds")
    timestamp: float = Field(..., description="Response timestamp")
    format: str = Field(..., description="Output format used")

class HealthResponse(BaseModel):
    """Response model for health checks."""
    timestamp: float = Field(..., description="Health check timestamp")
    overall_status: str = Field(..., description="Overall health status")
    components: Dict[str, Any] = Field(..., description="Component health status")
    processing_stats: Dict[str, Any] = Field(..., description="Processing statistics")
    issues: Optional[List[str]] = Field(None, description="List of issues found")

class StatsResponse(BaseModel):
    """Response model for statistics."""
    total_processed: int = Field(..., description="Total analyses processed")
    entities_extracted: int = Field(..., description="Total entities extracted")
    sentiment_analyses: int = Field(..., description="Total sentiment analyses")
    bias_detections: int = Field(..., description="Total bias detections")
    average_processing_time: float = Field(..., description="Average processing time")
    uptime: float = Field(..., description="Service uptime in seconds")

# Global startup time
startup_time = time.time()

# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    logger.info("🔍 Starting Analyst Agent - Quantitative Analysis Engine")
    logger.info("📊 Focus: Entity extraction, statistical analysis, sentiment/bias detection")
    logger.info("🎯 Specialization: Text metrics, trend analysis, GPU-accelerated NLP")
    logger.info("🤝 Integration: Works with Scout for content analysis, Synthesizer for insights")

    try:
        # Register with MCP Bus if available
        if MCP_AVAILABLE:
            await register_with_mcp_bus()

        logger.info("✅ Analyst Agent started successfully")

        yield

    except Exception as e:
        logger.error(f"❌ Failed to start Analyst Agent: {e}")
        raise
    finally:
        logger.info("🛑 Analyst Agent shutdown completed")

async def register_with_mcp_bus():
    """Register agent with MCP Bus."""
    if not MCP_AVAILABLE:
        logger.warning("MCP Bus client not available - skipping registration")
        return

    try:
        mcp_bus_url = MCP_BUS_URL
        client = MCPBusClient(mcp_bus_url)

        agent_info = {
            "name": "analyst",
            "description": "Quantitative news content analysis with GPU acceleration",
            "version": "2.0.0",
            "capabilities": [
                "entity_extraction",
                "text_statistics",
                "key_metrics",
                "trend_analysis",
                "sentiment_analysis",
                "bias_detection",
                "combined_analysis"
            ],
            "endpoints": {
                "identify_entities": "/identify_entities",
                "analyze_text_statistics": "/analyze_text_statistics",
                "extract_key_metrics": "/extract_key_metrics",
                "analyze_content_trends": "/analyze_content_trends",
                "analyze_sentiment": "/analyze_sentiment",
                "detect_bias": "/detect_bias",
                "analyze_sentiment_and_bias": "/analyze_sentiment_and_bias",
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
    title="Analyst Agent",
    description="Quantitative analysis engine for news content processing",
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

# Initialize metrics
try:
    metrics = JustNewsMetrics("analyst")
    # Metrics middleware
    app.middleware("http")(metrics.request_middleware)
except Exception as e:
    logger.warning(f"Metrics initialization failed: {e}")
    metrics = None

@app.get("/")
async def root():
    """Root endpoint with basic information."""
    return {
        "name": "Analyst Agent",
        "version": "2.0.0",
        "description": "Quantitative analysis engine for news content",
        "status": "running",
        "capabilities": [
            "entity_extraction",
            "text_statistics",
            "sentiment_analysis",
            "bias_detection",
            "trend_analysis"
        ]
    }

@app.post("/identify_entities", response_model=AnalysisResponse)
async def identify_entities_endpoint(request: EntitiesRequest):
    """
    Extract named entities from text content.

    This endpoint identifies and categorizes named entities such as persons,
    organizations, locations, dates, and other proper nouns in the provided text.
    """
    start_time = time.time()

    try:
        logger.info(f"🔍 Processing entity extraction request: {len(request.text)} characters")

        # Perform analysis
        result = identify_entities(request.text)

        # Validate result
        if not validate_analysis_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_analysis_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = AnalysisResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output
        )

        logger.info(f"✅ Entity extraction completed: {processing_time:.2f}s")
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Entity extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Entity extraction failed: {str(e)}")

@app.post("/analyze_text_statistics", response_model=AnalysisResponse)
async def analyze_text_statistics_endpoint(request: StatisticsRequest):
    """
    Perform comprehensive statistical analysis of text content.

    This endpoint analyzes various text metrics including word count, sentence
    structure, readability scores, vocabulary diversity, and complexity indicators.
    """
    start_time = time.time()

    try:
        logger.info(f"📊 Processing text statistics request: {len(request.text)} characters")

        # Perform analysis
        result = analyze_text_statistics(request.text)

        # Validate result
        if not validate_analysis_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_analysis_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = AnalysisResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output
        )

        logger.info(f"✅ Text statistics analysis completed: {processing_time:.2f}s")
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Text statistics analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Text statistics analysis failed: {str(e)}")

@app.post("/extract_key_metrics", response_model=AnalysisResponse)
async def extract_key_metrics_endpoint(request: MetricsRequest):
    """
    Extract key numerical and statistical metrics from news text.

    This endpoint identifies financial metrics, temporal references,
    statistical data, and geographic information in news content.
    """
    start_time = time.time()

    try:
        logger.info(f"🔍 Processing key metrics extraction: {len(request.text)} characters")

        # Perform analysis
        result = extract_key_metrics(request.text, request.url)

        # Validate result
        if not validate_analysis_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_analysis_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = AnalysisResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output
        )

        logger.info(f"✅ Key metrics extraction completed: {processing_time:.2f}s")
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Key metrics extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Key metrics extraction failed: {str(e)}")

@app.post("/analyze_content_trends", response_model=AnalysisResponse)
async def analyze_content_trends_endpoint(request: TrendsRequest):
    """
    Analyze trends and patterns across multiple content pieces.

    This endpoint identifies common entities, trending topics, and patterns
    across a collection of news articles or content pieces.
    """
    start_time = time.time()

    try:
        logger.info(f"📈 Processing content trends analysis: {len(request.texts)} texts")

        # Perform analysis
        result = analyze_content_trends(request.texts, request.urls)

        # Validate result
        if not validate_analysis_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_analysis_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = AnalysisResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output
        )

        logger.info(f"✅ Content trends analysis completed: {processing_time:.2f}s")
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Content trends analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Content trends analysis failed: {str(e)}")

@app.post("/analyze_sentiment", response_model=AnalysisResponse)
async def analyze_sentiment_endpoint(request: SentimentRequest):
    """
    Analyze sentiment of text content.

    This endpoint determines the overall sentiment (positive, negative, neutral)
    of the provided text using advanced NLP models with GPU acceleration.
    """
    start_time = time.time()

    try:
        logger.info(f"😊 Processing sentiment analysis: {len(request.text)} characters")

        # Perform analysis
        result = analyze_sentiment(request.text)

        # Validate result
        if not validate_analysis_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_analysis_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = AnalysisResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output
        )

        logger.info(f"✅ Sentiment analysis completed: {processing_time:.2f}s")
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Sentiment analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sentiment analysis failed: {str(e)}")

@app.post("/detect_bias", response_model=AnalysisResponse)
async def detect_bias_endpoint(request: BiasRequest):
    """
    Detect bias in text content.

    This endpoint analyzes text for potential bias indicators including
    political bias, emotional bias, and factual bias using advanced models.
    """
    start_time = time.time()

    try:
        logger.info(f"⚖️ Processing bias detection: {len(request.text)} characters")

        # Perform analysis
        result = detect_bias(request.text)

        # Validate result
        if not validate_analysis_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_analysis_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = AnalysisResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output
        )

        logger.info(f"✅ Bias detection completed: {processing_time:.2f}s")
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Bias detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bias detection failed: {str(e)}")

@app.post("/analyze_sentiment_and_bias", response_model=AnalysisResponse)
async def analyze_sentiment_and_bias_endpoint(request: CombinedAnalysisRequest):
    """
    Perform comprehensive analysis combining sentiment and bias detection.

    This endpoint provides a complete analysis including individual sentiment
    and bias assessments plus combined reliability scoring and recommendations.
    """
    start_time = time.time()

    try:
        logger.info(f"🔍 Processing combined sentiment and bias analysis: {len(request.text)} characters")

        # Perform analysis
        result = analyze_sentiment_and_bias(request.text)

        # Validate result
        if not validate_analysis_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_analysis_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = AnalysisResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output
        )

        logger.info(f"✅ Combined analysis completed: {processing_time:.2f}s")
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Combined analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Combined analysis failed: {str(e)}")

@app.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """Health check endpoint for monitoring and load balancers."""
    try:
        health_result = await health_check()
        return HealthResponse(**health_result)
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/stats", response_model=StatsResponse)
async def stats_endpoint():
    """Get processing statistics and performance metrics."""
    try:
        from .tools import get_analyst_engine
        engine = get_analyst_engine()

        uptime = time.time() - startup_time

        stats = StatsResponse(
            total_processed=engine.processing_stats['total_processed'],
            entities_extracted=engine.processing_stats['entities_extracted'],
            sentiment_analyses=engine.processing_stats['sentiment_analyses'],
            bias_detections=engine.processing_stats['bias_detections'],
            average_processing_time=engine.processing_stats['average_processing_time'],
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
        "name": "Analyst Agent",
        "version": "2.0.0",
        "capabilities": [
            "entity_extraction",
            "text_statistics",
            "key_metrics_extraction",
            "content_trends_analysis",
            "sentiment_analysis",
            "bias_detection",
            "combined_sentiment_bias_analysis"
        ],
        "supported_formats": ["json", "text", "markdown"],
        "gpu_acceleration": True,
        "max_text_length": 1000000,
        "supported_languages": ["en"],
        "models": {
            "entity_extraction": "spaCy en_core_web_sm + BERT fallback",
            "sentiment_analysis": "cardiffnlp/twitter-roberta-base-sentiment-latest",
            "bias_detection": "unitary/toxic-bert"
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

    host = os.environ.get("ANALYST_HOST", "0.0.0.0")
    port = int(os.environ.get("ANALYST_PORT", "8004"))
    reload_flag = os.environ.get("UVICORN_RELOAD", os.environ.get("ANALYST_RELOAD", "false")).lower() == "true"
    log_level = os.environ.get("UVICORN_LOG_LEVEL", os.environ.get("ANALYST_LOG_LEVEL", "info"))

    target = f"{__package__}.main:app" if __package__ else "main:app"

    logger.info(
        "Starting Analyst Service on %s:%s (reload=%s)",
        host,
        port,
        reload_flag,
    )

    uvicorn.run(
        target,
        host=host,
        port=port,
        reload=reload_flag,
        log_level=log_level,
    )