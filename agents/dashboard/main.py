"""
Main file for the Dashboard Agent.
"""

from typing import Any

import os
import sys
import time
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from fastapi import (
    FastAPI,
    HTTPException,
    Request,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from common.observability import get_logger

# Ensure the current package directory is on sys.path so sibling modules can be imported
# This makes `from config import load_config` work when running the FastAPI app directly.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import config module
try:
    from .config import load_config, save_config
except ImportError:
    # Fallback for direct execution
    def load_config():
        return {
            "dashboard_port": 8013,
            "mcp_bus_url": "http://localhost:8000",
            "gpu_config": {}
        }

    def save_config(config):
        pass


# Import production GPU manager
try:
    from agents.common.gpu_manager_production import get_gpu_manager
    GPU_MANAGER_AVAILABLE = True
except ImportError:
    GPU_MANAGER_AVAILABLE = False
    get_gpu_manager = None

# Import storage module
try:
    from .storage import get_storage
except ImportError:
    # Fallback for direct execution
    import sys
    storage_path = Path(__file__).parent / "storage.py"
    if storage_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("storage", storage_path)
        storage_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(storage_module)
        get_storage = storage_module.get_storage
    else:
        # Mock storage if not available
        def get_storage():
            class MockStorage:
                def store_gpu_metrics(self, data): pass
                def get_gpu_metrics_history(self, *args, **kwargs): return []
                def get_agent_allocation_history(self, *args, **kwargs): return []
                def get_performance_trends(self, *args, **kwargs): return []
                def get_recent_alerts(self, *args, **kwargs): return []
                def get_storage_stats(self, *args, **kwargs): return {}
            return MockStorage()
        get_storage = get_storage

# Import public API
try:
    from .public_api import include_public_api
    PUBLIC_API_AVAILABLE = True
except ImportError:
    PUBLIC_API_AVAILABLE = False

    def include_public_api(app):
        logger.warning("Public API not available")

# Import metrics library
from common.metrics import JustNewsMetrics

# Configure logging

logger = get_logger(__name__)

# Load configuration
config = load_config()
# Default dashboard port set to 8014 for public website (8013 was internal dashboard)
DASHBOARD_AGENT_PORT = config.get("dashboard_port", 8014)
MCP_BUS_URL = config.get("mcp_bus_url", "http://localhost:8000")
GPU_ORCHESTRATOR_URL = os.environ.get("GPU_ORCHESTRATOR_URL", "http://localhost:8014").rstrip("/")


class MCPBusClient:
    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list):
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            response = requests.post(f"{self.base_url}/register", json=registration_data)
            response.raise_for_status()
            logger.info(f"Successfully registered {agent_name} with MCP Bus.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register {agent_name} with MCP Bus: {e}")
            raise


class EnhancedGPUMonitor:
    """Enhanced GPU monitoring class integrated with production GPU manager."""

    def __init__(self):
        self.gpu_history = []
        self.max_history_size = 100
        self.gpu_manager = get_gpu_manager() if GPU_MANAGER_AVAILABLE else None

    def get_gpu_info(self) -> dict:
        """Get current GPU information using production GPU manager."""
        try:
            # If orchestrator present, prefer orchestrator snapshot for base telemetry
            orchestrator_snapshot = None
            try:
                orchestrator_snapshot = fetch_orchestrator_gpu_info()
            except Exception:
                orchestrator_snapshot = None

            if self.gpu_manager:
                # Use production GPU manager for comprehensive data
                system_status = self.gpu_manager.get_system_status()
                gpu_statuses = system_status.get('gpu_statuses', [])

                if gpu_statuses:
                    gpus = []
                    for status in gpu_statuses:
                        gpu_info = {
                            'index': status['device_id'],
                            'name': f"GPU {status['device_id']}",  # Could be enhanced to get actual name
                            'memory_used_mb': int(status['used_memory_gb'] * 1024),
                            'memory_total_mb': int(status['total_memory_gb'] * 1024),
                            'memory_free_mb': int(status['free_memory_gb'] * 1024),
                            'gpu_utilization_percent': int(status['utilization_percent']),
                            'memory_utilization_percent': int((status['used_memory_gb'] / status['total_memory_gb']) * 100) if status['total_memory_gb'] > 0 else 0,
                            'temperature_celsius': int(status['temperature_c']),
                            'fan_speed_percent': 0,  # Not available from manager
                            'power_draw_watts': int(status['power_draw_w']),
                            'power_limit_watts': 0,  # Not available from manager
                            'is_healthy': status['is_healthy'],
                            'timestamp': time.time()
                        }
                        gpus.append(gpu_info)

                    # Store in history
                    current_data = {
                        'timestamp': time.time(),
                        'gpus': gpus
                    }
                    self.gpu_history.append(current_data)
                    if len(self.gpu_history) > self.max_history_size:
                        self.gpu_history.pop(0)

                    response_payload = {
                        'status': 'success',
                        'gpu_count': len(gpus),
                        'gpus': gpus,
                        'timestamp': time.time(),
                    }
                    if orchestrator_snapshot is not None:
                        response_payload['orchestrator'] = orchestrator_snapshot
                    return response_payload
                else:
                    return {
                        'status': 'error',
                        'message': 'No GPU status data available from manager',
                        'timestamp': time.time()
                    }
            else:
                # Fallback to nvidia-smi if manager not available
                fallback = self._get_nvidia_smi_fallback()
                if orchestrator_snapshot is not None:
                    fallback['orchestrator'] = orchestrator_snapshot
                return fallback

        except Exception as e:
            logger.error(f"Error getting GPU info from manager: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': time.time()
            }

    def _get_nvidia_smi_fallback(self) -> dict:
        """Fallback GPU monitoring using nvidia-smi."""
        try:
            import subprocess
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=index,name,memory.used,memory.total,memory.free,utilization.gpu,utilization.memory,temperature.gpu,fan.speed,power.draw,power.limit',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                gpus = []
                for line in lines:
                    if line.strip():
                        parts = [part.strip() for part in line.split(',')]
                        if len(parts) >= 10:
                            gpu_info = {
                                'index': int(parts[0]),
                                'name': parts[1],
                                'memory_used_mb': int(parts[2]),
                                'memory_total_mb': int(parts[3]),
                                'memory_free_mb': int(parts[4]),
                                'gpu_utilization_percent': int(parts[5]),
                                'memory_utilization_percent': int(parts[6]),
                                'temperature_celsius': int(parts[7]),
                                'fan_speed_percent': int(parts[8]) if parts[8] != '[Not Supported]' else 0,
                                'power_draw_watts': float(parts[9]) if parts[9] != '[Not Supported]' else 0.0,
                                'power_limit_watts': float(parts[10]) if len(parts) > 10 and parts[10] != '[Not Supported]' else 0.0,
                                'is_healthy': True,  # Assume healthy if nvidia-smi works
                                'timestamp': time.time()
                            }
                            gpus.append(gpu_info)

                # Store in history
                current_data = {
                    'timestamp': time.time(),
                    'gpus': gpus
                }
                self.gpu_history.append(current_data)
                if len(self.gpu_history) > self.max_history_size:
                    self.gpu_history.pop(0)

                # Store data in historical storage
                try:
                    storage.store_gpu_metrics(current_data)
                except Exception as e:
                    logger.warning(f"Failed to store GPU metrics: {e}")

                return {
                    'status': 'success',
                    'gpu_count': len(gpus),
                    'gpus': gpus,
                    'timestamp': time.time()
                }
            else:
                return {
                    'status': 'error',
                    'message': f'nvidia-smi command failed: {result.stderr}',
                    'timestamp': time.time()
                }
        except Exception as e:
            logger.error(f"Error getting GPU info: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': time.time()
            }

    def get_gpu_history(self, hours: int = 1) -> list[dict]:
        """Get GPU history for the specified number of hours."""
        cutoff_time = time.time() - (hours * 3600)
        return [entry for entry in self.gpu_history if entry['timestamp'] >= cutoff_time]

    def get_agent_gpu_usage(self) -> dict:
        """Get GPU usage statistics per agent using production GPU manager."""
        try:
            if self.gpu_manager:
                # Get allocation data from production manager
                system_status = self.gpu_manager.get_system_status()
                allocations = system_status.get('active_allocations', 0)

                # Get per-agent allocation details
                agent_ports = {
                    'scout': 8002,
                    'fact_checker': 8003,
                    'analyst': 8004,
                    'synthesizer': 8005,
                    'critic': 8006,
                    'memory': 8007,
                    'newsreader': 8009
                }

                agent_usage = {}
                total_memory_used = 0

                for agent_name, port in agent_ports.items():
                    try:
                        # Check if agent is active
                        response = requests.get(f"http://localhost:{port}/health", timeout=2)
                        is_active = response.status_code == 200
                    except (requests.RequestException, ConnectionError, TimeoutError) as e:
                        logger.debug(f"Failed to check agent {agent_name} health: {e}")
                        is_active = False

                    # Get allocation status from GPU manager
                    allocation_status = None
                    if self.gpu_manager:
                        allocation_status = self.gpu_manager.get_allocation_status(agent_name)

                    if allocation_status:
                        memory_used = allocation_status.get('allocated_memory_gb', 0) * 1024  # Convert to MB
                        gpu_util = 0  # Could be enhanced with actual utilization tracking
                    else:
                        # Mock data based on agent type and activity
                        base_usage = {
                            'scout': {'memory_mb': 800, 'utilization_percent': 15},
                            'fact_checker': {'memory_mb': 600, 'utilization_percent': 12},
                            'analyst': {'memory_mb': 400, 'utilization_percent': 8},
                            'synthesizer': {'memory_mb': 1000, 'utilization_percent': 20},
                            'critic': {'memory_mb': 500, 'utilization_percent': 10},
                            'memory': {'memory_mb': 300, 'utilization_percent': 6},
                            'newsreader': {'memory_mb': 900, 'utilization_percent': 18}
                        }.get(agent_name, {'memory_mb': 0, 'utilization_percent': 0})

                        memory_used = base_usage['memory_mb'] if is_active else 0
                        gpu_util = base_usage['utilization_percent'] if is_active else 0

                    agent_usage[agent_name] = {
                        'active': is_active,
                        'memory_used_mb': memory_used,
                        'gpu_utilization_percent': gpu_util,
                        'allocation_status': allocation_status,
                        'last_updated': time.time()
                    }

                    if is_active:
                        total_memory_used += memory_used

                return {
                    'status': 'success',
                    'agents': agent_usage,
                    'total_memory_used_mb': total_memory_used,
                    'active_allocations': allocations,
                    'gpu_manager_available': True,
                    'timestamp': time.time()
                }
            else:
                # Fallback to basic agent checking
                return self._get_agent_gpu_usage_fallback()

        except Exception as e:
            logger.error(f"Error getting agent GPU usage: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': time.time()
            }

    def _get_agent_gpu_usage_fallback(self) -> dict:
        """Fallback agent GPU usage when GPU manager not available."""
        try:
            agent_ports = {
                'scout': 8002,
                'fact_checker': 8003,
                'analyst': 8004,
                'synthesizer': 8005,
                'critic': 8006,
                'memory': 8007,
                'newsreader': 8009
            }

            agent_usage = {}
            total_memory_used = 0

            for agent_name, port in agent_ports.items():
                try:
                    # Check if agent is active
                    response = requests.get(f"http://localhost:{port}/health", timeout=2)
                    is_active = response.status_code == 200
                except (requests.RequestException, ConnectionError, TimeoutError) as e:
                    logger.debug(f"Failed to check agent {agent_name} health (fallback): {e}")
                    is_active = False

                # Mock GPU usage based on agent type and activity
                base_usage = {
                    'scout': {'memory_mb': 800, 'utilization_percent': 15},
                    'fact_checker': {'memory_mb': 600, 'utilization_percent': 12},
                    'analyst': {'memory_mb': 400, 'utilization_percent': 8},
                    'synthesizer': {'memory_mb': 1000, 'utilization_percent': 20},
                    'critic': {'memory_mb': 500, 'utilization_percent': 10},
                    'memory': {'memory_mb': 300, 'utilization_percent': 6},
                    'newsreader': {'memory_mb': 900, 'utilization_percent': 18}
                }.get(agent_name, {'memory_mb': 0, 'utilization_percent': 0})

                memory_used = base_usage['memory_mb'] if is_active else 0
                gpu_util = base_usage['utilization_percent'] if is_active else 0

                agent_usage[agent_name] = {
                    'active': is_active,
                    'memory_used_mb': memory_used,
                    'gpu_utilization_percent': gpu_util,
                    'last_updated': time.time()
                }

                if is_active:
                    total_memory_used += memory_used

            return {
                'status': 'success',
                'agents': agent_usage,
                'total_memory_used_mb': total_memory_used,
                'gpu_manager_available': False,
                'timestamp': time.time()
            }
        except Exception as e:
            logger.error(f"Error getting agent GPU usage fallback: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': time.time()
            }


# Global enhanced GPU monitor instance
gpu_monitor = EnhancedGPUMonitor()

# Global storage instance
storage = get_storage()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Dashboard agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="dashboard",
            agent_address=f"http://localhost:{DASHBOARD_AGENT_PORT}",
            tools=["get_status", "send_command", "receive_logs", "get_gpu_info", "get_gpu_history", "get_agent_gpu_usage", "get_gpu_config", "update_gpu_config"],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield
    logger.info("Dashboard agent is shutting down.")
    save_config(config)

app = FastAPI(lifespan=lifespan)

# Add CORS middleware for public API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for public website
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Include public API routes
if PUBLIC_API_AVAILABLE:
    include_public_api(app)

# Initialize metrics
metrics = JustNewsMetrics("dashboard")

ready = False

# Register shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for dashboard")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for dashboard")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)


class ToolCall(BaseModel):
    args: list
    kwargs: dict[str, Any]


@app.get("/get_status")
def get_status():
    """Fetch the status of all agents."""
    try:
        response = requests.get(f"{MCP_BUS_URL}/agents")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"An error occurred while fetching agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "agent": "dashboard"}


@app.get("/ready")
def ready_endpoint():
    return {"ready": ready}


@app.get("/")
def dashboard_home():
    """Serve the main JustNews public website"""
    try:
        # Try to serve the public website HTML file first
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            return FileResponse(public_website_path, media_type="text/html")
        else:
            # Fall back to embedded HTML
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving public website: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.get("/article/{article_id}")
def serve_article_page(article_id: str):
    """Serve individual article page"""
    try:
        # Try to serve the public website HTML file with article context
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            with open(public_website_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Add article ID to the page for JavaScript to handle
            content = content.replace(
                '<body>',
                f'<body data-article-id="{article_id}">'
            )
            return HTMLResponse(content=content)
        else:
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving article page: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.get("/search")
def serve_search_page(request: Request):
    """Serve search results page"""
    try:
        query = request.query_params.get('q', '')
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            with open(public_website_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Add search query to the page for JavaScript to handle
            content = content.replace(
                '<body>',
                f'<body data-search-query="{query}">'
            )
            return HTMLResponse(content=content)
        else:
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving search page: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.get("/about")
def serve_about_page():
    """Serve about page"""
    try:
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            with open(public_website_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Add about flag to the page for JavaScript to handle
            content = content.replace(
                '<body>',
                '<body data-page="about">'
            )
            return HTMLResponse(content=content)
        else:
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving about page: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.get("/api-docs")
def serve_api_docs():
    """Serve API documentation page"""
    try:
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            with open(public_website_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Add API docs flag to the page for JavaScript to handle
            content = content.replace(
                '<body>',
                '<body data-page="api-docs">'
            )
            return HTMLResponse(content=content)
        else:
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving API docs page: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.post("/send_command")
def send_command(call: ToolCall):
    """Send a command to another agent."""
    try:
        # Use model_dump() for Pydantic v2 compatibility; fall back to dict() when unavailable
        response = requests.post(
            f"{MCP_BUS_URL}/call",
            json=(call.model_dump() if hasattr(call, "model_dump") else call.dict()),
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"An error occurred while sending a command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GPU Monitoring Endpoints

@app.get("/gpu/info")
def get_gpu_info():
    """Get current GPU information and status."""
    try:
        gpu_info = gpu_monitor.get_gpu_info()
        return gpu_info
    except Exception as e:
        logger.error(f"Error in get_gpu_info endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/history")
def get_gpu_history(hours: int = 1):
    """Get GPU usage history for the specified number of hours."""
    try:
        history = gpu_monitor.get_gpu_history(hours)
        return {
            "status": "success",
            "hours": hours,
            "data_points": len(history),
            "history": history,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Error in get_gpu_history endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/agents")
def get_agent_gpu_usage():
    """Get GPU usage statistics per agent."""
    try:
        agent_usage = gpu_monitor.get_agent_gpu_usage()
        return agent_usage
    except Exception as e:
        logger.error(f"Error in get_agent_gpu_usage endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/config")
def get_gpu_config():
    """Get current GPU configuration from the GPU manager."""
    try:
        # Try to get config from GPU manager
        response = requests.get("http://localhost:8000/gpu/config", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            # Fallback to local config
            return {
                "status": "success",
                "source": "dashboard_fallback",
                "config": config.get("gpu_config", {}),
                "timestamp": time.time()
            }
    except Exception as e:
        logger.error(f"Error getting GPU config: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        }


@app.post("/gpu/config")
def update_gpu_config(new_config: dict):
    """Update GPU configuration."""
    try:
        # Try to update via GPU manager
        response = requests.post("http://localhost:8000/gpu/config", json=new_config, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            # Fallback to local update
            if "gpu_config" not in config:
                config["gpu_config"] = {}
            config["gpu_config"].update(new_config)
            save_config(config)
            return {
                "status": "success",
                "source": "dashboard_fallback",
                "message": "Configuration updated locally",
                "config": config["gpu_config"],
                "timestamp": time.time()
            }
    except Exception as e:
        logger.error(f"Error updating GPU config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/manager/status")
def get_gpu_manager_status():
    """Get comprehensive GPU manager system status."""
    try:
        if gpu_monitor.gpu_manager:
            system_status = gpu_monitor.gpu_manager.get_system_status()
            return {
                'status': 'success',
                'gpu_manager_available': True,
                'system_status': system_status,
                'timestamp': time.time()
            }
        else:
            return {
                'status': 'success',
                'gpu_manager_available': False,
                'message': 'GPU manager not available, using fallback monitoring',
                'timestamp': time.time()
            }
    except Exception as e:
        logger.error(f"Error getting GPU manager status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/allocations")
def get_gpu_allocations():
    """Get all current GPU allocations."""
    try:
        if gpu_monitor.gpu_manager:
            # Get allocation data from GPU manager
            allocations = []
            agent_names = ['scout', 'fact_checker', 'analyst', 'synthesizer', 'critic', 'memory', 'newsreader']

            for agent_name in agent_names:
                allocation_status = gpu_monitor.gpu_manager.get_allocation_status(agent_name)
                if allocation_status:
                    allocations.append(allocation_status)

            return {
                'status': 'success',
                'allocations': allocations,
                'total_allocations': len(allocations),
                'timestamp': time.time()
            }
        else:
            return {
                'status': 'success',
                'gpu_manager_available': False,
                'allocations': [],
                'message': 'GPU manager not available',
                'timestamp': time.time()
            }
    except Exception as e:
        logger.error(f"Error getting GPU allocations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/metrics")
def get_gpu_metrics():
    """Get GPU performance metrics from the manager."""
    try:
        if gpu_monitor.gpu_manager:
            system_status = gpu_monitor.gpu_manager.get_system_status()
            metrics = system_status.get('metrics', {})

            return {
                'status': 'success',
                'gpu_manager_available': True,
                'metrics': metrics,
                'timestamp': time.time()
            }
        else:
            return {
                'status': 'success',
                'gpu_manager_available': False,
                'metrics': {},
                'message': 'GPU manager not available',
                'timestamp': time.time()
            }
    except Exception as e:
        logger.error(f"Error getting GPU metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class IngestRequest(BaseModel):
    """Request model for ingesting external GPU metrics JSONL."""
    path: str
    max_lines: int | None = 10000


def _parse_iso8601_to_epoch(ts_str: str) -> float:
    """Convert ISO8601 string to epoch seconds; fallback to time.time() on failure."""
    try:
        # Handle timezone-aware timestamps
        from datetime import datetime
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        try:
            import dateutil.parser  # type: ignore
            return dateutil.parser.isoparse(ts_str).timestamp()
        except Exception:
            return time.time()


@app.post("/gpu/ingest_jsonl")
def ingest_gpu_jsonl(req: IngestRequest):
    """Ingest GPU watcher JSONL into dashboard storage.

    Supports records with shape:
      {"time": "...", "gpus": [{"index": 0, "name": "RTX 3090", "memory_used_mib": 2333, "utilization_percent": 35, "temperature_c": 30, "power_watts": 36.2, ...}], ...}

    Unknown fields are ignored. Units: *_mib are treated as MB.
    """
    try:
        in_path = req.path
        if not os.path.isabs(in_path):
            # Resolve relative to project root
            in_path = str((Path(__file__).resolve().parents[2] / req.path).resolve())

        if not os.path.exists(in_path):
            raise HTTPException(status_code=404, detail=f"File not found: {in_path}")

        ingested_points = 0
        max_lines = req.max_lines or 10000

        with open(in_path, "r", encoding="utf-8", errors="ignore") as fh:
            import json
            # First attempt: line-by-line JSONL
            any_line_parsed = False
            for i, line in enumerate(fh):
                if i >= max_lines:
                    break
                s = line.strip().rstrip(",")
                if not s or s.startswith("#"):
                    continue
                try:
                    record = json.loads(s)
                    _ingest_single_gpu_record(record)
                    ingested_points += 1
                    any_line_parsed = True
                except Exception:
                    # Continue; we'll try a blob parse after the loop
                    pass

            if not any_line_parsed:
                # Second attempt: parse entire blob (wrapped formats)
                fh.seek(0)
                blob = fh.read()
                # Heuristic cleanup for known artifacts from older watcher: remove "[," after array openers
                blob_clean = (
                    blob.replace('gpus": [,', 'gpus": [')
                        .replace('processes": [,', 'processes": [')
                )
                try:
                    data = json.loads(blob_clean)
                except Exception:
                    # As a last resort, try to split by lines and parse portions that look like JSON
                    data = None
                    candidates = []
                    for chunk in blob_clean.splitlines():
                        t = chunk.strip().rstrip(",")
                        if t.startswith("{") and t.endswith("}"):
                            candidates.append(t)
                    for t in candidates[:max_lines]:
                        try:
                            rec = json.loads(t)
                            _ingest_single_gpu_record(rec)
                            ingested_points += 1
                        except Exception:
                            continue

                if isinstance(data, dict):
                    # Support known containers: records, samples
                    if "records" in data and isinstance(data["records"], list):
                        for rec in data["records"][:max_lines]:
                            _ingest_single_gpu_record(rec)
                            ingested_points += 1
                    elif "samples" in data and isinstance(data["samples"], list):
                        for rec in data["samples"][:max_lines]:
                            _ingest_single_gpu_record(rec)
                            ingested_points += 1
                elif isinstance(data, list):
                    for rec in data[:max_lines]:
                        _ingest_single_gpu_record(rec)
                        ingested_points += 1

        return {"status": "success", "ingested_records": ingested_points, "path": in_path, "timestamp": time.time()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting GPU JSONL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _ingest_single_gpu_record(record: dict) -> None:
    """Normalize and store a single GPU watcher record into storage."""
    try:
        ts = record.get("time") or record.get("timestamp") or time.time()
        if isinstance(ts, str):
            epoch = _parse_iso8601_to_epoch(ts)
        elif isinstance(ts, (int, float)):
            epoch = float(ts)
        else:
            epoch = time.time()

        gpus = []
        for g in record.get("gpus", []):
            # Map possible keys from watcher to dashboard schema
            mem_used_mb = g.get("memory_used_mb")
            if mem_used_mb is None:
                mem_used_mb = g.get("memory_used_mib") or g.get("memory_used")
            mem_total_mb = g.get("memory_total_mb")
            if mem_total_mb is None:
                mem_total_mb = g.get("memory_total_mib") or g.get("memory.total")
            mem_free_mb = g.get("memory_free_mb")
            if mem_free_mb is None:
                mem_free_mb = g.get("memory_free_mib") or g.get("memory.free")

            util = g.get("gpu_utilization_percent")
            if util is None:
                util = g.get("utilization_percent") or g.get("utilization.gpu")

            temp_c = g.get("temperature_celsius")
            if temp_c is None:
                temp_c = g.get("temperature_c") or g.get("temperature.gpu")

            power_w = g.get("power_draw_watts")
            if power_w is None:
                power_w = g.get("power_watts") or g.get("power.draw")

            # Convert MiB to MB if needed (treat values as already MiB/MB; store as float)
            def _to_float(v):
                try:
                    return float(v)
                except Exception:
                    return None

            gpu_info = {
                "index": g.get("index") or g.get("id") or 0,
                "name": g.get("name") or f"GPU {g.get('index', 0)}",
                "memory_used_mb": _to_float(mem_used_mb),
                "memory_total_mb": _to_float(mem_total_mb),
                "memory_free_mb": _to_float(mem_free_mb),
                "gpu_utilization_percent": int(_to_float(util) or 0),
                "memory_utilization_percent": None,
                "temperature_celsius": int(_to_float(temp_c) or 0),
                "fan_speed_percent": _to_float(g.get("fan_speed_percent") or g.get("fan.speed")) or 0,
                "power_draw_watts": _to_float(power_w) or 0.0,
                "power_limit_watts": _to_float(g.get("power_limit_watts") or g.get("power.limit")) or 0.0,
                "is_healthy": True,
                "timestamp": epoch,
            }

            # Compute memory utilization if possible
            if gpu_info["memory_used_mb"] is not None and gpu_info["memory_total_mb"]:
                try:
                    gpu_info["memory_utilization_percent"] = int((gpu_info["memory_used_mb"] / gpu_info["memory_total_mb"]) * 100)
                except Exception:
                    gpu_info["memory_utilization_percent"] = None

            gpus.append(gpu_info)

        if gpus:
            storage.store_gpu_metrics({"gpus": gpus})
    except Exception as e:
        logger.warning(f"Failed to ingest single GPU record: {e}")


@app.get("/gpu/dashboard")
def get_gpu_dashboard_data():
    """Get comprehensive GPU dashboard data including manager integration."""
    try:
        gpu_info = gpu_monitor.get_gpu_info()
        orchestrator_policy = None
        try:
            orchestrator_policy = fetch_orchestrator_policy()
        except Exception:
            orchestrator_policy = None
        agent_usage = gpu_monitor.get_agent_gpu_usage()
        gpu_config = get_gpu_config()

        # Get additional data from GPU manager if available
        manager_status = None
        allocations = []
        metrics = {}

        if gpu_monitor.gpu_manager:
            manager_status = gpu_monitor.gpu_manager.get_system_status()

            # Get allocations
            agent_names = ['scout', 'fact_checker', 'analyst', 'synthesizer', 'critic', 'memory', 'newsreader']
            for agent_name in agent_names:
                allocation_status = gpu_monitor.gpu_manager.get_allocation_status(agent_name)
                if allocation_status:
                    allocations.append(allocation_status)

            metrics = manager_status.get('metrics', {})

        # Calculate enhanced summary
        summary = {
            "total_gpus": gpu_info.get("gpu_count", 0),
            "total_memory_used_mb": agent_usage.get("total_memory_used_mb", 0),
            "active_agents": sum(1 for agent in agent_usage.get("agents", {}).values() if agent.get("active", False)),
            "gpu_utilization_avg": sum(gpu.get("gpu_utilization_percent", 0) for gpu in gpu_info.get("gpus", [])) / max(1, len(gpu_info.get("gpus", []))),
            "gpu_manager_available": gpu_monitor.gpu_manager is not None,
            "active_allocations": len(allocations),
            "total_allocation_requests": metrics.get('total_allocations', 0),
            "successful_allocations": metrics.get('successful_allocations', 0),
            "failed_allocations": metrics.get('failed_allocations', 0),
            "cpu_fallbacks": metrics.get('cpu_fallbacks', 0),
            "gpu_recoveries": metrics.get('gpu_recoveries', 0)
        }

        return {
            "status": "success",
            "timestamp": time.time(),
            "gpu_info": gpu_info,
            "agent_usage": agent_usage,
            "gpu_config": gpu_config,
            "gpu_manager": {
                "available": gpu_monitor.gpu_manager is not None,
                "status": manager_status,
                "allocations": allocations,
                "metrics": metrics
            },
            "orchestrator_policy": orchestrator_policy,
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error in get_gpu_dashboard_data endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/history/db")
def get_gpu_history_from_db(hours: int = 24, gpu_index: int | None = None, metric: str = "utilization"):
    """Get GPU metrics history from database."""
    try:
        if metric == "utilization":
            history = storage.get_gpu_metrics_history(hours, gpu_index, metric_type="utilization")
        elif metric == "memory":
            history = storage.get_gpu_metrics_history(hours, gpu_index, metric_type="memory_used_mb")
        elif metric == "temperature":
            history = storage.get_gpu_metrics_history(hours, gpu_index, metric_type="temperature_celsius")
        elif metric == "performance":
            # For performance, we'll use processing time or similar metrics
            history = storage.get_performance_trends(hours)
        else:
            history = storage.get_gpu_metrics_history(hours, gpu_index)

        # Format data for Chart.js
        formatted_data = []
        for entry in history:
            if metric == "utilization":
                value = entry.get('gpu_utilization_percent', 0)
            elif metric == "memory":
                value = entry.get('memory_used_mb', 0) / 1024  # Convert to GB
            elif metric == "temperature":
                value = entry.get('temperature_celsius', 0)
            elif metric == "performance":
                value = entry.get('processing_time_ms', 0)
            else:
                value = entry.get('gpu_utilization_percent', 0)

            formatted_data.append({
                'timestamp': entry.get('timestamp', 0),
                'value': value
            })

        return {
            'status': 'success',
            'hours': hours,
            'gpu_index': gpu_index,
            'metric': metric,
            'data_points': len(formatted_data),
            'data': formatted_data,
            'timestamp': time.time()
        }
    except Exception as e:
        logger.error(f"Error getting GPU history from DB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/allocations/history")
def get_allocation_history(hours: int = 24, agent_name: str | None = None):
    """Get agent allocation history from database."""
    try:
        history = storage.get_agent_allocation_history(hours, agent_name)
        return {
            'status': 'success',
            'hours': hours,
            'agent_name': agent_name,
            'data_points': len(history),
            'history': history,
            'timestamp': time.time()
        }
    except Exception as e:
        logger.error(f"Error getting allocation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/trends")
def get_performance_trends(hours: int = 24):
    """Get performance trends data."""
    try:
        trends = storage.get_performance_trends(hours)
        return {
            'status': 'success',
            'hours': hours,
            'trends': trends,
            'timestamp': time.time()
        }
    except Exception as e:
        logger.error(f"Error getting performance trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu/alerts")
def get_recent_alerts(limit: int = 50):
    """Get recent alerts from database."""
    try:
        alerts = storage.get_recent_alerts(limit)
        return {
            'status': 'success',
            'limit': limit,
            'alerts': alerts,
            'total_alerts': len(alerts),
            'timestamp': time.time()
        }
    except Exception as e:
        logger.error(f"Error getting recent alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/storage/stats")
def get_storage_stats():
    """Get database storage statistics."""
    try:
        stats = storage.get_storage_stats()
        return {
            'status': 'success',
            'storage_stats': stats,
            'timestamp': time.time()
        }
    except Exception as e:
        logger.error(f"Error getting storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_fallback_dashboard_html():
    """Fallback HTML dashboard if template file is not available."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>JustNewsAgent GPU Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .metric { background: #f0f0f0; padding: 10px; margin: 10px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>🚀 JustNewsAgent GPU Dashboard</h1>
        <div id="dashboard">
            <div class="metric">
                <h3>GPU Status</h3>
                <p>Loading...</p>
            </div>
        </div>
        <button onclick="loadData()">Refresh</button>

        <script>
            async function loadData() {
                try {
                    const response = await fetch('/gpu/dashboard');
                    const data = await response.json();
                    updateDashboard(data);
                } catch (error) {
                    console.error('Error:', error);
                }
            }

            function updateDashboard(data) {
                const dashboard = document.getElementById('dashboard');
                if (data.status === 'success') {
                    dashboard.innerHTML = `
                        <div class="metric">
                            <h3>GPU Summary</h3>
                            <p>Total GPUs: ${data.summary.total_gpus}</p>
                            <p>Active Agents: ${data.summary.active_agents}</p>
                            <p>Avg Utilization: ${data.summary.gpu_utilization_avg.toFixed(1)}%</p>
                        </div>
                    `;
                }
            }

            // Auto-refresh every 5 seconds
            setInterval(loadData, 5000);
            loadData();
        </script>
    </body>
    </html>
    """


def get_fallback_public_website_html():
    """Fallback HTML for public JustNews website if template file is not available."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>JustNews - AI-Powered News Analysis</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .hero-section { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 100px 0; }
            .news-card { transition: transform 0.2s; border: none; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .news-card:hover { transform: translateY(-5px); }
            .credibility-badge { position: absolute; top: 10px; right: 10px; padding: 5px 10px; border-radius: 20px; font-size: 0.8em; font-weight: bold; }
            .credibility-high { background: #28a745; color: white; }
            .credibility-medium { background: #ffc107; color: black; }
            .credibility-low { background: #dc3545; color: white; }
        </style>
    </head>
    <body>
        <!-- Navigation -->
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container">
                <a class="navbar-brand" href="#">
                    <i class="fas fa-newspaper"></i> JustNews
                </a>
                <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                    <span class="navbar-toggler-icon"></span>
                </button>
                <div class="collapse navbar-collapse" id="navbarNav">
                    <ul class="navbar-nav me-auto">
                        <li class="nav-item"><a class="nav-link active" href="#news">News</a></li>
                        <li class="nav-item"><a class="nav-link" href="#analysis">Analysis</a></li>
                        <li class="nav-item"><a class="nav-link" href="#sources">Sources</a></li>
                        <li class="nav-item"><a class="nav-link" href="#api">API</a></li>
                    </ul>
                    <form class="d-flex">
                        <input class="form-control me-2" type="search" placeholder="Search news..." id="searchInput">
                        <button class="btn btn-outline-light" type="button" onclick="searchNews()">Search</button>
                    </form>
                </div>
            </div>
        </nav>

        <!-- Hero Section -->
        <section class="hero-section">
            <div class="container text-center">
                <h1 class="display-4 mb-4">AI-Powered News Analysis</h1>
                <p class="lead mb-4">Discover news with transparent AI analysis, credibility scoring, and fact-checking</p>
                <div class="row text-center">
                    <div class="col-md-4">
                        <i class="fas fa-brain fa-3x mb-3"></i>
                        <h5>AI Analysis</h5>
                        <p>Sentiment, bias, and topic analysis</p>
                    </div>
                    <div class="col-md-4">
                        <i class="fas fa-shield-alt fa-3x mb-3"></i>
                        <h5>Fact Checking</h5>
                        <p>Source credibility and verification</p>
                    </div>
                    <div class="col-md-4">
                        <i class="fas fa-chart-line fa-3x mb-3"></i>
                        <h5>Transparency</h5>
                        <p>Open data and research APIs</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- News Feed -->
        <section class="py-5" id="news">
            <div class="container">
                <h2 class="text-center mb-4">Latest News</h2>
                <div class="row" id="newsContainer">
                    <div class="col-12 text-center">
                        <div class="spinner-border" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p>Loading news articles...</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- Footer -->
        <footer class="bg-dark text-light py-4">
            <div class="container text-center">
                <p>&copy; 2025 JustNews. AI-powered news analysis platform.</p>
                <p>Built with transparency, accuracy, and trust.</p>
            </div>
        </footer>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            // Load news articles
            async function loadNews() {
                try {
                    const response = await fetch('/api/public/articles');
                    const data = await response.json();
                    displayNews(data.articles || []);
                } catch (error) {
                    console.error('Error loading news:', error);
                    document.getElementById('newsContainer').innerHTML = '<div class="col-12 text-center"><p class="text-muted">Unable to load news articles at this time.</p></div>';
                }
            }

            function displayNews(articles) {
                const container = document.getElementById('newsContainer');
                if (articles.length === 0) {
                    container.innerHTML = '<div class="col-12 text-center"><p class="text-muted">No articles available.</p></div>';
                    return;
                }

                container.innerHTML = articles.map(article => `
                    <div class="col-md-6 col-lg-4 mb-4">
                        <div class="card news-card h-100 position-relative">
                            <div class="credibility-badge credibility-${getCredibilityClass(article.source_credibility)}">
                                ${article.source_credibility}% Credible
                            </div>
                            <div class="card-body">
                                <h5 class="card-title">${article.title}</h5>
                                <p class="card-text text-muted">${article.summary}</p>
                                <div class="mb-2">
                                    <small class="text-muted">
                                        <i class="fas fa-user"></i> ${article.source} |
                                        <i class="fas fa-clock"></i> ${new Date(article.published_date).toLocaleDateString()}
                                    </small>
                                </div>
                                <div class="mb-2">
                                    <span class="badge bg-primary">${article.sentiment_score > 0 ? 'Positive' : article.sentiment_score < 0 ? 'Negative' : 'Neutral'}</span>
                                    <span class="badge bg-info">Fact Check: ${article.fact_check_score}%</span>
                                </div>
                                <p class="card-text"><small class="text-muted">${article.topics.join(', ')}</small></p>
                            </div>
                        </div>
                    </div>
                `).join('');
            }

            function getCredibilityClass(score) {
                if (score >= 80) return 'high';
                if (score >= 60) return 'medium';
                return 'low';
            }

            function searchNews() {
                const query = document.getElementById('searchInput').value;
                if (query.trim()) {
                    window.location.href = `/search?q=${encodeURIComponent(query)}`;
                }
            }

            // Load news on page load
            document.addEventListener('DOMContentLoaded', loadNews);
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", 8013))

    logger.info(f"Starting Dashboard Agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


# Orchestrator proxy helpers & endpoints (added after __main__ for clarity; executed on import)
import requests as _requests  # noqa: E402


def fetch_orchestrator_gpu_info():
    """Fetch GPU info from orchestrator (fast timeout)."""
    try:
        r = _requests.get(f"{GPU_ORCHESTRATOR_URL}/gpu/info", timeout=(1.5, 3.0))
        if r.status_code == 200:
            return r.json()
        return {"available": False, "error": f"unexpected_status:{r.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": str(e)}


def fetch_orchestrator_policy():
    """Fetch policy from orchestrator (fast timeout)."""
    try:
        r = _requests.get(f"{GPU_ORCHESTRATOR_URL}/policy", timeout=(1.5, 3.0))
        if r.status_code == 200:
            return r.json()
        return {"safe_mode_read_only": True, "error": f"unexpected_status:{r.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"safe_mode_read_only": True, "error": str(e)}


@app.get("/orchestrator/gpu/info")
def orchestrator_gpu_info_proxy():
    """Proxy to orchestrator /gpu/info with fallback."""
    return fetch_orchestrator_gpu_info()


@app.get("/orchestrator/gpu/policy")
def orchestrator_gpu_policy_proxy():
    """Proxy to orchestrator /policy with fallback."""
    return fetch_orchestrator_policy()


@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    return Response(metrics.get_metrics(), media_type="text/plain")


# Crawler Control Endpoints

class CrawlRequest(BaseModel):
    domains: list[str]
    max_sites: int = 5
    max_articles_per_site: int = 10
    concurrent_sites: int = 3
    strategy: str = "auto"
    enable_ai: bool = True
    timeout: int = 300
    user_agent: str = "JustNewsAgent/1.0"


@app.post("/api/crawl/start")
async def start_crawl(request: CrawlRequest):
    """Start a new crawl job"""
    try:
        # Use MCP bus to call the crawler agent
        payload = {
            "agent": "crawler",
            "tool": "unified_production_crawl",
            "args": [request.domains],
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
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to start crawl: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start crawl: {str(e)}")

@app.get("/api/crawl/status")
async def get_crawl_status():
    """Get current crawl job statuses"""
    try:
        # Use MCP bus to get crawler status
        payload = {
            "agent": "crawler",
            "tool": "get_jobs",
            "args": [],
            "kwargs": {}
        }
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=5)
        response.raise_for_status()
        jobs = response.json()
        
        # Get details for each job
        job_details = {}
        for job_id, status in jobs.items():
            try:
                detail_payload = {
                    "agent": "crawler",
                    "tool": "get_job_status",
                    "args": [job_id],
                    "kwargs": {}
                }
                detail_response = requests.post(f"{MCP_BUS_URL}/call", json=detail_payload, timeout=5)
                detail_response.raise_for_status()
                job_details[job_id] = detail_response.json()
            except Exception:
                job_details[job_id] = {"status": "unknown"}
        
        return job_details
    except requests.RequestException as e:
        logger.error(f"Failed to get crawl status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get crawl status: {str(e)}")

@app.get("/api/metrics/crawler")
async def get_crawler_metrics():
    """Get crawler performance metrics"""
    try:
        # Use MCP bus to get crawler metrics
        payload = {
            "agent": "crawler",
            "tool": "get_metrics",
            "args": [],
            "kwargs": {}
        }
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=5)
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
        # Use MCP bus to get analyst metrics
        payload = {
            "agent": "analyst",
            "tool": "get_metrics",
            "args": [],
            "kwargs": {}
        }
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=5)
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
        # Use MCP bus to get memory metrics
        payload = {
            "agent": "memory",
            "tool": "get_metrics",
            "args": [],
            "kwargs": {}
        }
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=5)
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
        ("crawler", 8015),  # Assuming crawler port
        ("analyst", 8004),
        ("memory", 8007),
        ("mcp_bus", 8000)
    ]
    
    for name, port in agents:
        try:
            response = requests.get(f"http://localhost:{port}/health", timeout=2)
            health[name] = response.status_code == 200
        except Exception:
            health[name] = False
    
    return health
