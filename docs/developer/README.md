# JustNewsAgent Developer Documentation

## Architecture Overview

JustNewsAgent is a distributed multi-agent system for automated news analysis, featuring GPU acceleration, continuous learning, and comprehensive monitoring.

## System Architecture

### Core Components

#### MCP Bus (Model Context Protocol Bus)
- **Role**: Central communication hub coordinating all agents
- **Technology**: FastAPI with async message passing
- **Port**: 8000
- **Responsibilities**:
  - Agent registration and discovery
  - Inter-agent communication routing
  - Health monitoring and load balancing
  - Message queuing and reliability

#### Specialized Agents
Each agent is a microservice with specific responsibilities:

- **Chief Editor (Port 8001)**: Workflow orchestration and system coordination
- **Scout (Port 8002)**: Content discovery and web crawling
- **Fact Checker (Port 8003)**: Source verification and fact-checking
- **Analyst (Port 8004)**: GPU-accelerated sentiment and bias analysis
- **Synthesizer (Port 8005)**: Content synthesis and summarization
- **Critic (Port 8006)**: Quality assessment and review
- **Memory (Port 8007)**: Data persistence and vector search
- **Reasoning (Port 8008)**: Symbolic logic and reasoning

#### Supporting Services
- **Dashboard (Port 8013)**: Web interface and real-time monitoring
- **Public API (Port 8014)**: External API for news data access
- **Archive API (Port 8021)**: RESTful archive with legal compliance
- **GraphQL API (Port 8020)**: Advanced query interface

### Data Flow Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   News Sources  │───▶│     Scout       │───▶│    Fact Checker │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Analyst      │◀───│  Chief Editor   │───▶│     Memory      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Synthesizer    │    │     Critic      │    │   Reasoning     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              └────────────────────────┘
                                       │
                                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Public APIs   │    │   Dashboard     │    │   Monitoring    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Technology Stack

#### Core Framework
- **FastAPI**: High-performance async web framework
- **Pydantic V2**: Type-safe data validation and serialization
- **SQLAlchemy**: Database ORM with async support
- **Redis**: Caching and session management

#### AI/ML Stack
- **PyTorch 2.6+**: Deep learning framework with CUDA 12.4
- **Transformers**: Pre-trained models and tokenizers
- **Sentence Transformers**: Text embedding and similarity
- **TensorRT**: GPU inference optimization
- **NVIDIA MPS**: GPU memory sharing and isolation

#### Data Processing
- **MariaDB**: Primary relational data storage
- **ChromaDB**: Vector similarity search and embeddings
- **Pandas/Polars**: Data manipulation and analysis
- **NumPy**: Numerical computing

#### Infrastructure
- **Docker**: Containerization
- **Kubernetes**: Container orchestration
- **Prometheus/Grafana**: Monitoring and alerting
- **Nginx**: Reverse proxy and load balancing

## Agent Development Guide

### Agent Structure Pattern

All agents follow a consistent structure:

```
agents/{agent_name}/
├── __init__.py
├── main.py              # FastAPI application
├── tools.py             # Agent-specific tools
├── models.py            # Pydantic models
├── config.py            # Agent configuration
├── requirements.txt     # Dependencies
└── tests/
    ├── __init__.py
    ├── test_main.py
    └── test_tools.py
```

### Agent Implementation Template

```python
# agents/my_agent/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
import asyncio

from common.mcp_client import MCPBusClient
from common.metrics import JustNewsMetrics
from common.config import get_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize components
app = FastAPI(title="My Agent", version="1.0.0")
config = get_config()
metrics = JustNewsMetrics(agent="my_agent")
mcp_client = MCPBusClient()

# Pydantic models
class ToolCall(BaseModel):
    """Standard MCP tool call format"""
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}

class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: float

# Global state
start_time = asyncio.get_event_loop().time()

@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    try:
        # Register with MCP Bus
        await mcp_client.register_agent(
            name="my_agent",
            endpoint=f"http://localhost:{config.port}",
            capabilities=["my_tool"]
        )
        logger.info("Agent registered with MCP Bus")
    except Exception as e:
        logger.error(f"Failed to register agent: {e}")
        raise

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        uptime=asyncio.get_event_loop().time() - start_time
    )

@app.post("/my_tool")
async def my_tool_endpoint(call: ToolCall):
    """Main tool endpoint"""
    try:
        # Record metrics
        metrics.increment("tool_calls", {"tool": "my_tool"})

        # Execute tool logic
        result = await my_tool_function(*call.args, **call.kwargs)

        # Record success
        metrics.increment("tool_success", {"tool": "my_tool"})

        return {
            "status": "success",
            "data": result,
            "timestamp": asyncio.get_event_loop().time()
        }

    except Exception as e:
        # Record error
        metrics.increment("tool_errors", {"tool": "my_tool", "error": str(e)})
        logger.error(f"Tool execution failed: {e}")

        raise HTTPException(
            status_code=500,
            detail=f"Tool execution failed: {str(e)}"
        )

# Tool implementation
async def my_tool_function(param1: str, param2: int = 0) -> Dict[str, Any]:
    """Implement your tool logic here"""
    # Example implementation
    return {
        "param1": param1,
        "param2": param2,
        "result": f"Processed {param1} with {param2}"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.port,
        reload=config.debug
    )
```

### MCP Bus Integration

#### Agent Registration
```python
from common.mcp_client import MCPBusClient

mcp_client = MCPBusClient()

# Register agent
await mcp_client.register_agent(
    name="my_agent",
    endpoint="http://localhost:8009",
    capabilities=["tool1", "tool2"]
)
```

#### Inter-Agent Communication
```python
# Call another agent
result = await mcp_client.call_agent(
    agent="memory",
    tool="save_article",
    article_data=my_article
)

# Call with error handling
try:
    result = await mcp_client.call_agent(
        agent="analyst",
        tool="analyze_sentiment",
        text=article_text,
        timeout=30.0
    )
except MCPTimeoutError:
    logger.warning("Analysis timeout, using fallback")
    result = fallback_analysis(article_text)
```

### Configuration Management

#### Agent Configuration
```python
# agents/my_agent/config.py
from common.config import BaseAgentConfig

class MyAgentConfig(BaseAgentConfig):
    """Configuration for My Agent"""

    # Agent-specific settings
    model_name: str = "default-model"
    batch_size: int = 32
    timeout: float = 30.0

    # GPU settings
    gpu_memory_limit: int = 4096  # MB
    use_tensorrt: bool = True

    # Performance tuning
    max_concurrent_requests: int = 10
    cache_ttl: int = 3600  # seconds
```

#### Configuration Usage
```python
from .config import MyAgentConfig

config = MyAgentConfig()

# Access configuration
model = load_model(config.model_name)
batch_size = config.batch_size
```

### Error Handling Patterns

#### Structured Error Handling
```python
class AgentError(Exception):
    """Base agent error"""
    pass

class ValidationError(AgentError):
    """Input validation error"""
    pass

class ProcessingError(AgentError):
    """Processing error"""
    pass

@app.post("/my_tool")
async def my_tool_endpoint(call: ToolCall):
    try:
        # Validate input
        if not call.args:
            raise ValidationError("Args cannot be empty")

        # Process request
        result = await process_request(call)

        return {"status": "success", "data": result}

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ProcessingError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Testing Patterns

#### Unit Tests
```python
# tests/test_my_agent.py
import pytest
from agents.my_agent.main import my_tool_function, app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_my_tool_function():
    """Test tool function logic"""
    result = my_tool_function("test", param2=42)
    assert result["param1"] == "test"
    assert result["param2"] == 42

def test_my_tool_endpoint():
    """Test API endpoint"""
    response = client.post("/my_tool", json={
        "args": ["test"],
        "kwargs": {"param2": 42}
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
```

#### Integration Tests
```python
# tests/test_integration.py
import pytest
from tests.mcp_scaffold import MCPTestServer

@pytest.fixture
async def mcp_server():
    server = MCPTestServer()
    await server.start()
    yield server
    await server.stop()

@pytest.mark.asyncio
async def test_agent_registration(mcp_server):
    """Test agent registration with MCP bus"""
    # Start agent
    agent_server = await start_test_agent()

    # Register with test MCP server
    await mcp_server.register_agent("my_agent", agent_server.url)

    # Verify registration
    agents = await mcp_server.get_agents()
    assert "my_agent" in agents

    # Test tool call
    result = await mcp_server.call_agent("my_agent", "my_tool", "test")
    assert result["status"] == "success"
```

### Performance Optimization

#### GPU Memory Management
```python
import torch
from contextlib import asynccontextmanager

@asynccontextmanager
async def gpu_context():
    """GPU memory management context"""
    try:
        # Allocate GPU memory
        torch.cuda.empty_cache()
        yield
    finally:
        # Clean up
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

async def gpu_operation():
    async with gpu_context():
        # GPU operations here
        model = load_model_to_gpu()
        result = model.process(data)
        return result
```

#### Async Processing
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Thread pool for CPU-bound operations
cpu_executor = ThreadPoolExecutor(max_workers=4)

async def process_batch(items: List[Dict]) -> List[Dict]:
    """Process items in parallel batches"""
    semaphore = asyncio.Semaphore(config.max_concurrent_requests)

    async def process_item(item: Dict) -> Dict:
        async with semaphore:
            # Offload CPU-bound work to thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                cpu_executor,
                cpu_bound_processing,
                item
            )
            return result

    # Process all items concurrently
    tasks = [process_item(item) for item in items]
    results = await asyncio.gather(*tasks)
    return results
```

### Monitoring & Metrics

#### Custom Metrics
```python
from common.metrics import JustNewsMetrics

metrics = JustNewsMetrics(agent="my_agent")

# Counter metrics
metrics.increment("requests_total", {"endpoint": "/my_tool"})

# Gauge metrics
metrics.gauge("active_requests", len(active_requests))

# Histogram metrics
metrics.histogram("request_duration", duration, {"endpoint": "/my_tool"})

# Custom metric
metrics.set("gpu_memory_used", gpu_memory_mb)
```

#### Health Checks
```python
@app.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe"""
    try:
        # Check dependencies
        await check_database_connection()
        await check_mcp_bus_connection()

        # Check GPU if required
        if config.requires_gpu:
            await check_gpu_availability()

        return {"status": "ready"}

    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Not ready")

@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=metrics.generate_prometheus_output(),
        media_type="text/plain"
    )
```

## Development Workflow

### Local Development
```bash
# Setup development environment
make setup-dev

# Run agent locally
python -m agents.my_agent.main

# Run with hot reload
uvicorn agents.my_agent.main:app --reload --port 8009

# Run tests
pytest tests/ -v

# Check code quality
ruff check .
mypy agents/my_agent/
```

### Testing Strategy
1. **Unit Tests**: Test individual functions and classes
2. **Integration Tests**: Test agent-to-agent communication
3. **Performance Tests**: Test under load with realistic data
4. **E2E Tests**: Full workflow testing with MCP bus

### Recent changes (Oct–Nov 2025)

- Adaptive Crawl4AI integration: The crawler adapter (`agents/crawler/crawl4ai_adapter.py`) can now invoke `AdaptiveCrawler` using profile-provided `adaptive` settings and `extra.query` hints. Adaptive results are mapped back to existing article structures and annotated with `extraction_metadata.crawl4ai.adaptive_run` for auditing.
- Metrics & observability: Adaptive telemetry is recorded via the Stage B metrics helpers. The `common.metrics` module is tolerant of environments missing optional GPU helper libraries (`GPUtil`) and exposes compatibility helpers (`increment`, `gauge`, `timing`) used by legacy test harnesses.
- Developer test notes: New unit tests were added under `tests/agents/crawler/` for the Crawl4AI adapter; run `pytest tests/agents/crawler -q` to exercise adapter-specific behavior. Integration tests for memory and ingestion were also updated.

### Code Quality Standards
- **PEP 8**: 88-character line limit
- **Type Hints**: Required for all function signatures
- **Docstrings**: Google-style for all public functions
- **Error Handling**: Comprehensive exception handling
- **Logging**: Structured logging with appropriate levels

### Deployment Pipeline
1. **Code Review**: PR review with automated checks
2. **CI/CD**: Automated testing and building
3. **Staging**: Deploy to staging environment
4. **Integration Testing**: End-to-end validation
5. **Production**: Rolling deployment with monitoring

---

*Developer Documentation Version: 1.0.0*
*Last Updated: October 22, 2025*