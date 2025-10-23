"""
Advanced Analytics Dashboard for JustNewsAgent

Provides comprehensive web-based analytics interface with:
- Real-time performance monitoring
- Historical trend analysis
- Agent performance profiling
- System health monitoring
- Bottleneck detection and recommendations
- Interactive charts and visualizations
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..common.advanced_analytics import get_analytics_engine

# Initialize analytics engine
analytics_engine = get_analytics_engine()

# FastAPI app for analytics dashboard
analytics_app = FastAPI(title="JustNewsAgent Advanced Analytics Dashboard")

# Templates and static files
templates_dir = Path(__file__).parent / "analytics" / "templates"
static_dir = Path(__file__).parent / "analytics" / "static"

templates_dir.mkdir(parents=True, exist_ok=True)
static_dir.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(templates_dir))

# Mount static files
analytics_app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@analytics_app.get("/", response_class=HTMLResponse)
async def analytics_dashboard(request: Request):
    """Main analytics dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@analytics_app.get("/api/health")
async def get_system_health():
    """Get system health metrics"""
    try:
        health = analytics_engine.get_system_health_score()
        return JSONResponse(content=health)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@analytics_app.get("/api/realtime/{hours}")
async def get_realtime_analytics(hours: int = 1):
    """Get real-time analytics for specified hours"""
    try:
        if hours < 1 or hours > 24:
            raise HTTPException(status_code=400, detail="Hours must be between 1 and 24")

        analytics = analytics_engine.get_real_time_analytics(hours=hours)
        return JSONResponse(content=analytics.__dict__)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics retrieval failed: {str(e)}")

@analytics_app.get("/api/agent/{agent_name}/{hours}")
async def get_agent_profile(agent_name: str, hours: int = 24):
    """Get performance profile for specific agent"""
    try:
        if hours < 1 or hours > 168:  # Max 1 week
            raise HTTPException(status_code=400, detail="Hours must be between 1 and 168")

        profile = analytics_engine.get_agent_performance_profile(agent_name, hours=hours)
        return JSONResponse(content=profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent profile retrieval failed: {str(e)}")

@analytics_app.get("/api/trends/{hours}")
async def get_performance_trends(hours: int = 24):
    """Get performance trends analysis"""
    try:
        analytics = analytics_engine.get_real_time_analytics(hours=hours)
        return JSONResponse(content={
            "trends": analytics.performance_trends,
            "bottlenecks": analytics.bottleneck_indicators,
            "recommendations": analytics.optimization_recommendations
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trends analysis failed: {str(e)}")

@analytics_app.get("/api/report/{hours}")
async def get_analytics_report(hours: int = 24):
    """Get comprehensive analytics report"""
    try:
        report = analytics_engine.export_analytics_report(hours=hours)
        return JSONResponse(content=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

@analytics_app.get("/api/optimization-recommendations")
async def get_optimization_recommendations(hours: int = 24):
    """Get advanced optimization recommendations"""
    try:
        from ..common.advanced_optimization import generate_optimization_recommendations

        recommendations = generate_optimization_recommendations(hours)
        return JSONResponse(content=[
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
        ])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization analysis failed: {str(e)}")

@analytics_app.get("/api/optimization-insights")
async def get_optimization_insights():
    """Get optimization insights and analytics"""
    try:
        from ..common.advanced_optimization import get_optimization_insights

        insights = get_optimization_insights()
        return JSONResponse(content=insights)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insights generation failed: {str(e)}")

@analytics_app.post("/api/record-metric")
async def record_custom_metric(metric_data: dict[str, Any]):
    """Record a custom performance metric"""
    try:
        from ..common.advanced_analytics import PerformanceMetrics

        # Validate required fields
        required_fields = ["agent_name", "operation", "processing_time_s", "batch_size", "success"]
        for field in required_fields:
            if field not in metric_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        # Create metric object
        metric = PerformanceMetrics(
            timestamp=datetime.now(),
            agent_name=metric_data["agent_name"],
            operation=metric_data["operation"],
            processing_time_s=float(metric_data["processing_time_s"]),
            batch_size=int(metric_data["batch_size"]),
            success=bool(metric_data["success"]),
            gpu_memory_allocated_mb=float(metric_data.get("gpu_memory_allocated_mb", 0.0)),
            gpu_memory_reserved_mb=float(metric_data.get("gpu_memory_reserved_mb", 0.0)),
            gpu_utilization_pct=float(metric_data.get("gpu_utilization_pct") or 0.0),
            temperature_c=float(metric_data.get("temperature_c") or 0.0),
            power_draw_w=float(metric_data.get("power_draw_w") or 0.0),
            throughput_items_per_s=float(metric_data.get("throughput_items_per_s", 0.0))
        )

        # Record the metric
        analytics_engine.record_metric(metric)

        return JSONResponse(content={"status": "success", "message": "Metric recorded successfully"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metric recording failed: {str(e)}")

def create_analytics_app() -> FastAPI:
    """Create and return the analytics dashboard FastAPI app"""
    return analytics_app

def start_analytics_dashboard(host: str = "0.0.0.0", port: int = 8012):
    """Start the analytics dashboard server"""
    import uvicorn
    uvicorn.run(analytics_app, host=host, port=port)

if __name__ == "__main__":
    start_analytics_dashboard()
