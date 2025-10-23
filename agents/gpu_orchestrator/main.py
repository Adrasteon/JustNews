"""
GPU Orchestrator Service

Centralized, conservative GPU coordination service with SAFE_MODE awareness.
Provides read-only GPU telemetry and placeholder allocation/policy endpoints
to be expanded in later phases. Designed to run under systemd via the
standard justnews-start-agent.sh launcher.
"""

import os
import subprocess
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
import uuid
import threading
import time
import logging

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from prometheus_client import (
    Counter, Gauge
)

from common.observability import get_logger

# Import metrics library
from common.metrics import JustNewsMetrics

# Import preload module
from .preload import start_preload_job, get_preload_status
from agents.gpu_orchestrator.preload import _MODEL_PRELOAD_STATE
from agents.gpu_orchestrator.nvml import get_nvml_handle


# Ensure the log level is set to DEBUG to capture all debug messages
logging.basicConfig(level=logging.DEBUG)

logger = get_logger(__name__)

# Environment configuration
GPU_ORCHESTRATOR_PORT = int(os.environ.get("GPU_ORCHESTRATOR_PORT", 8014))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
SAFE_MODE = os.environ.get("SAFE_MODE", "false").lower() == "true"
ENABLE_NVML = os.environ.get("ENABLE_NVML", "false").lower() == "true"
LEASE_TTL_SECONDS = int(os.environ.get("GPU_ORCHESTRATOR_LEASE_TTL", "3600"))  # 1 hour default; 0 disables TTL


# In-memory state (intentionally simple/minimal for safety)
READINESS: bool = False
POLICY: Dict[str, Any] = {
	"max_memory_per_agent_mb": 2048,
	"allow_fractional_shares": True,
	"kill_on_oom": False,
	"safe_mode_read_only": SAFE_MODE,
}
ALLOCATIONS: Dict[str, Dict[str, Any]] = {}

# Simple in-process metrics (avoid external deps). Prometheus exposition via /metrics.
_METRICS_COUNTERS: Dict[str, int] = {
	"requests_total": 0,
	"gpu_info_requests_total": 0,
	"policy_get_requests_total": 0,
	"policy_post_requests_total": 0,
	"lease_requests_total": 0,
	"release_requests_total": 0,
	"lease_expired_total": 0,
}
_START_TIME = time.time()
_NVML_SUPPORTED = False
_NVML_INIT_ERROR: Optional[str] = None
_NVML_HANDLE_CACHE = {}


def _inc(metric: str) -> None:
	_METRICS_COUNTERS[metric] = _METRICS_COUNTERS.get(metric, 0) + 1
	_METRICS_COUNTERS["requests_total"] = _METRICS_COUNTERS.get("requests_total", 0) + 1


def _purge_expired_leases() -> None:
	"""Remove expired leases based on LEASE_TTL_SECONDS.

	Executed opportunistically at read/write endpoints to avoid background threads.
	"""
	if LEASE_TTL_SECONDS <= 0 or not ALLOCATIONS:
		return
	now = time.time()
	expired: List[str] = []
	for token, alloc in list(ALLOCATIONS.items()):
		try:
			started = float(alloc.get("timestamp", now))
		except Exception:  # noqa: BLE001
			started = now
		if now - started > LEASE_TTL_SECONDS:
			expired.append(token)
	for token in expired:
		ALLOCATIONS.pop(token, None)
	if expired:
		_METRICS_COUNTERS["lease_expired_total"] = _METRICS_COUNTERS.get("lease_expired_total", 0) + len(expired)
		lease_expired_counter.labels(
			agent=metrics.agent_name,
			agent_display_name=metrics.display_name
		).inc(len(expired))


class MCPBusClient:
	def __init__(self, base_url: str = MCP_BUS_URL):
		self.base_url = base_url

	def register_agent(self, agent_name: str, agent_address: str, tools: List[str]):
		# Make 'requests' optional at import time so the agent can start in
		# constrained environments where the package is not installed.
		try:
			import requests
		except Exception:
			requests = None


		registration_data = {
			"name": agent_name,
			"address": agent_address,
			"tools": tools,
		}

		for attempt in range(5): # Retry up to 5 times
			try:
				if requests is None:
					logger.warning("Requests library not available; skipping MCP Bus registration attempt")
					return
				response = requests.post(f"{self.base_url}/register", json=registration_data, timeout=(2, 5))
				response.raise_for_status()
				logger.info(f"Successfully registered {agent_name} with MCP Bus on attempt {attempt + 1}")
				return
			except requests.exceptions.RequestException as e:
				logger.warning(f"MCP Bus unavailable for registration (attempt {attempt + 1}/5): {e}")
				time.sleep(2 ** attempt) # Exponential backoff

		logger.error(f"Failed to register {agent_name} with MCP Bus after multiple attempts.")


def _run_nvidia_smi() -> Optional[str]:
	"""Run nvidia-smi and return raw XML or CSV output, or None if unavailable."""
	# Prefer CSV for simpler parsing at this stage
	cmd = [
		"nvidia-smi",
		"--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw",
		"--format=csv,noheader,nounits",
	]
	try:
		output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=3)
		return output
	except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
		logger.debug(f"nvidia-smi unavailable or failed: {e}")
		return None


def _parse_nvidia_smi_csv(csv_text: str) -> List[Dict[str, Any]]:
	gpus: List[Dict[str, Any]] = []
	for line in csv_text.strip().splitlines():
		parts = [p.strip() for p in line.split(",")]
		if len(parts) < 7:
			continue
		try:
			gpus.append(
				{
					"index": int(parts[0]),
					"name": parts[1],
					"memory_total_mb": float(parts[2]),
					"memory_used_mb": float(parts[3]),
					"utilization_gpu_pct": float(parts[4]),
					"temperature_c": float(parts[5]),
					"power_draw_w": float(parts[6]),
					"memory_utilization_pct": (
						(float(parts[3]) / float(parts[2]) * 100.0) if float(parts[2]) > 0 else 0.0
					),
				}
			)
		except ValueError:
			# Skip malformed rows
			continue
	return gpus


def _get_nvml_enrichment(gpus: List[Dict[str, Any]]) -> None:
	"""Enrich GPU info with NVML data if available and enabled.

	Mutates the input list of GPU dictionaries to add NVML-related fields.
	"""
	if not ENABLE_NVML or SAFE_MODE or not _NVML_SUPPORTED:
		return
	try:
		import pynvml  # type: ignore
		for g in gpus:
			idx = g.get("index")
			if idx is not None:
				try:
					handle = get_nvml_handle(idx)
					util = pynvml.nvmlDeviceGetUtilizationRates(handle)
					mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
					g["nvml_gpu_util_pct"] = getattr(util, "gpu", None)
					g["nvml_mem_used_mb"] = round(mem.used / 1024**2, 2)
					g["nvml_mem_total_mb"] = round(mem.total / 1024**2, 2)
					g["nvml_mem_util_pct"] = round((mem.used / mem.total * 100.0) if mem.total else 0.0, 2)
				except Exception as e:  # noqa: BLE001
					g["nvml_error"] = str(e)
	except Exception as e:
		logger.warning(f"NVML enrichment error: {e}")


def get_gpu_snapshot() -> Dict[str, Any]:
	"""Return a conservative, read-only snapshot of GPU state."""
	smi = _run_nvidia_smi()
	if smi is None:
		return {"gpus": [], "available": False, "message": "nvidia-smi not available"}
	gpus = _parse_nvidia_smi_csv(smi)
	_get_nvml_enrichment(gpus)
	return {"gpus": gpus, "available": True, "nvml_enriched": bool(ENABLE_NVML and not SAFE_MODE and _NVML_SUPPORTED), "nvml_supported": _NVML_SUPPORTED}


def _detect_mps() -> Dict[str, Any]:
	"""Best-effort NVIDIA MPS detection.

	Returns a dict with:
	- enabled: bool
	- pipe_dir: str | None
	- control_process: bool (whether nvidia-cuda-mps-control appears active)
	"""
	pipe_dir = os.environ.get("CUDA_MPS_PIPE_DIRECTORY", "/tmp/nvidia-mps")
	control_process = False
	enabled = False
	try:
		out = subprocess.run([
			"pgrep", "-x", "nvidia-cuda-mps-control"
		], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
		control_process = (out.returncode == 0)
	except Exception:
		control_process = False
	try:
		if pipe_dir and os.path.exists(pipe_dir):
			enabled = True
	except Exception:
		enabled = False
	enabled = enabled or control_process
	return {"enabled": bool(enabled), "pipe_dir": pipe_dir, "control_process": bool(control_process)}


class PolicyUpdate(BaseModel):
	max_memory_per_agent_mb: Optional[int] = Field(None, ge=256, description="Per-agent memory cap in MB")
	allow_fractional_shares: Optional[bool] = None
	kill_on_oom: Optional[bool] = None

	class Config:
		arbitrary_types_allowed = True


class LeaseRequest(BaseModel):
	agent: str
	min_memory_mb: Optional[int] = Field(0, ge=0)

	model_config = ConfigDict(arbitrary_types_allowed=True)


class ReleaseRequest(BaseModel):
	token: str

	model_config = ConfigDict(arbitrary_types_allowed=True)


class PreloadRequest(BaseModel):
	agents: Optional[List[str]] = Field(default=None, description="Subset of agents to preload; default all from AGENT_MODEL_MAP.json")
	refresh: bool = Field(default=False, description="Restart preloading even if a job already completed")
	strict: Optional[bool] = Field(default=None, description="Override STRICT_MODEL_STORE env for this preload run")

	model_config = ConfigDict(arbitrary_types_allowed=True)


# Modify lifespan to delay readiness until registration completes
@asynccontextmanager
async def lifespan(app: FastAPI):
    global READINESS
    logger.info("GPU Orchestrator starting up")

    # Registration status tracker
    registration_complete = threading.Event()

    def register_agent_background(agent_name: str, agent_address: str, tools: List[str]):
        """Register the agent with the MCP Bus in a background thread."""
        def background_task():
            client = MCPBusClient()
            client.register_agent(agent_name, agent_address, tools)
            registration_complete.set()  # Signal registration completion

        thread = threading.Thread(target=background_task, daemon=True)
        thread.start()

    # Start background registration
    register_agent_background(
        agent_name="gpu_orchestrator",
        agent_address=f"http://localhost:{GPU_ORCHESTRATOR_PORT}",
        tools=[
            "health",
            "gpu_info",
            "get_policy",
            "set_policy",
            "get_allocations",
            "lease",
            "release",
            "models_preload",
            "models_status",
            "mps_allocation",
        ],
    )

    # Wait for registration to complete before signaling readiness
    logger.info("Waiting for MCP Bus registration to complete...")
    registration_complete.wait(timeout=30)  # Wait up to 30 seconds
    if registration_complete.is_set():
        logger.info("MCP Bus registration completed successfully.")
    else:
        logger.warning("MCP Bus registration did not complete within the timeout.")

    READINESS = True
    yield
    logger.info("GPU Orchestrator shutting down")


app = FastAPI(title="GPU Orchestrator", lifespan=lifespan)


# Initialize metrics
metrics = JustNewsMetrics("gpu_orchestrator")

# Set initial uptime
uptime_gauge = Gauge(
    'gpu_orchestrator_uptime_seconds',
    'GPU orchestrator uptime in seconds',
    ['agent', 'agent_display_name'],
    registry=metrics.registry
)
uptime_gauge.labels(
    agent=metrics.agent_name,
    agent_display_name=metrics.display_name
).set(time.time() - _START_TIME)

# Add MPS-specific metrics
mps_enabled_gauge = Gauge(
    'gpu_orchestrator_mps_enabled',
    'Whether NVIDIA MPS is enabled (1) or disabled (0)',
    ['agent', 'agent_display_name'],
    registry=metrics.registry
)

# Add additional GPU orchestrator specific metrics
lease_expired_counter = Counter(
    'gpu_orchestrator_lease_expired_total',
    'Total number of GPU leases that have expired',
    ['agent', 'agent_display_name'],
    registry=metrics.registry
)

nvml_supported_gauge = Gauge(
    'gpu_orchestrator_nvml_supported',
    'Whether NVML is supported and enabled (1) or not (0)',
    ['agent', 'agent_display_name'],
    registry=metrics.registry
)


# Optional shared endpoints if available
try:
	from agents.common.shutdown import register_shutdown_endpoint

	register_shutdown_endpoint(app)
except Exception:
	logger.debug("shutdown endpoint not registered for gpu_orchestrator")

try:
	from agents.common.reload import register_reload_endpoint

	register_reload_endpoint(app)
except Exception:
	logger.debug("reload endpoint not registered for gpu_orchestrator")


# Add metrics middleware
app.middleware("http")(metrics.request_middleware)

@app.get("/health")
@app.post("/health")
async def health(request: Request):
	_inc("policy_get_requests_total")  # reuse counter group for simplicity
	return {"status": "ok", "safe_mode": SAFE_MODE}


@app.get("/ready")
def ready():
	_inc("policy_get_requests_total")
	return {"ready": READINESS}


@app.get("/gpu/info")
def gpu_info():
	"""Return current GPU telemetry (read-only)."""
	try:
		_inc("gpu_info_requests_total")
		logger.info("Fetching GPU snapshot...")
		data = get_gpu_snapshot()
		logger.info(f"GPU snapshot data: {data}")

		if ENABLE_NVML and not SAFE_MODE and not _NVML_SUPPORTED:
			data["nvml_init_error"] = _NVML_INIT_ERROR or "unsupported"
			logger.warning(f"NVML not supported: {data['nvml_init_error']}")

		logger.info("Detecting MPS status...")
		mps = _detect_mps()
		logger.info(f"MPS detection result: {mps}")

		data["mps_enabled"] = bool(mps.get("enabled", False))
		data["mps"] = mps

		# Update MPS metrics
		mps_enabled_gauge.labels(
			agent=metrics.agent_name,
			agent_display_name=metrics.display_name
		).set(1 if data["mps_enabled"] else 0)

		logger.info("Returning GPU telemetry data.")
		return data
	except Exception as e:
		logger.error(f"Failed to get GPU snapshot: {e}")
		raise HTTPException(status_code=500, detail=str(e))


@app.get("/policy")
def get_policy():
	_inc("policy_get_requests_total")
	return POLICY


@app.post("/policy")
def set_policy(update: PolicyUpdate):
	if SAFE_MODE:
		# In SAFE_MODE, accept but do not enact changes (read-only posture)
		_inc("policy_post_requests_total")
		return {
			**POLICY,
			"note": "SAFE_MODE enabled: policy updates accepted but not enacted",
		}

	changed = False
	if update.max_memory_per_agent_mb is not None:
		POLICY["max_memory_per_agent_mb"] = int(update.max_memory_per_agent_mb)
		changed = True
	if update.allow_fractional_shares is not None:
		POLICY["allow_fractional_shares"] = bool(update.allow_fractional_shares)
		changed = True
	if update.kill_on_oom is not None:
		POLICY["kill_on_oom"] = bool(update.kill_on_oom)
		changed = True

	if changed:
		logger.info(f"Updated GPU policy: {POLICY}")
	_inc("policy_post_requests_total")
	return POLICY


@app.get("/allocations")
def get_allocations():
	"""Return current agent→GPU allocation view (placeholder)."""
	_inc("policy_get_requests_total")
	_purge_expired_leases()
	return {"allocations": ALLOCATIONS}


def _validate_lease_request(req: LeaseRequest) -> Optional[str]:
	"""Validate the lease request parameters.

	Returns an error message if validation fails, or None if valid.
	"""
	if req.min_memory_mb is not None and req.min_memory_mb < 0:
		return "min_memory_mb must be >= 0"
	return None


def _allocate_gpu(req: LeaseRequest) -> Tuple[bool, Optional[int]]:
	"""Allocate a GPU based on the lease request.

	Returns a tuple of (success, gpu_index) where success is a boolean
	indicating if the allocation was successful, and gpu_index is the
	index of the allocated GPU or None if no GPU could be allocated.
	"""
	snapshot = get_gpu_snapshot()
	if snapshot.get("available") and snapshot.get("gpus"):
		# naive: choose lowest used memory GPU meeting minimum
		candidates = []
		for g in snapshot["gpus"]:
			if req.min_memory_mb and (g["memory_total_mb"] - g["memory_used_mb"]) < req.min_memory_mb:
				continue
			candidates.append(g)
		if candidates:
			return True, sorted(candidates, key=lambda x: x["memory_used_mb"])[0]["index"]
	return False, None


@app.post("/lease")
def lease(req: LeaseRequest):
    """Obtain a simple ephemeral GPU lease. SAFE_MODE returns note only.

    Strategy: first-fit; if no GPU info or none available, return cpu fallback.
    NOT a hard guarantee—placeholder for future sophisticated allocator.
    """
    _inc("lease_requests_total")
    _purge_expired_leases()
    if SAFE_MODE:
        return {"granted": False, "note": "SAFE_MODE", "agent": req.agent}

    # Validate request
    err = _validate_lease_request(req)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # Allocate GPU
    success, gpu_index = _allocate_gpu(req)
    token = str(uuid.uuid4())
    allocation = {
        "agent": req.agent,
        "gpu": gpu_index if success else "cpu",
        "token": token,
        "timestamp": time.time(),
    }
    ALLOCATIONS[token] = allocation

    # Ensure `granted` is True for CPU fallback
    return {"granted": True, **allocation}


@app.post("/release")
def release(req: ReleaseRequest):
	_inc("release_requests_total")
	_purge_expired_leases()
	alloc = ALLOCATIONS.pop(req.token, None)
	if not alloc:
		raise HTTPException(status_code=404, detail="unknown_token")
	return {"released": True, "token": req.token}


@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response
    return Response(metrics.get_metrics(), media_type="text/plain")


# ---------------------------
# Model preload functionality
# ---------------------------

def _project_root() -> str:
	try:
		import pathlib
		return str(pathlib.Path(__file__).resolve().parents[2])
	except Exception:
		return os.getcwd()


def _read_agent_model_map() -> Dict[str, Any]:
	"""Read the agent model map from AGENT_MODEL_MAP.json.

	Returns a dictionary mapping agent names to lists of model IDs.
	"""
	try:
		import json
		from pathlib import Path
		
		project_root = Path(__file__).resolve().parents[2]
		model_map_path = project_root / "AGENT_MODEL_MAP.json"
		
		if not model_map_path.exists():
			logger.warning(f"Model map file not found: {model_map_path}")
			return {}
		
		with open(model_map_path, "r") as f:
			model_map = json.load(f)
		
		logger.info(f"Loaded agent model map: {model_map}")
		return model_map
	except Exception as e:
		logger.error(f"Failed to read agent model map: {e}")
		return {}


def _validate_and_load_model(agent: str, model_id: str, strict: bool) -> Tuple[bool, Optional[str]]:
    """Validate and load a model for an agent.

    Returns a tuple of (success, error_message) where success is a boolean
    indicating if the validation and loading was successful, and error_message
    is an optional string containing the error reason if it failed.
    """
    try:
        # Attempt to load the model using the mocked function
        from agents.common.model_loader import load_sentence_transformer
        logger.info(f"Validating and loading model {model_id} for agent {agent} (strict={strict})")
        success, error = load_sentence_transformer(model_id, agent=agent)
        logger.debug(f"load_sentence_transformer returned: success={success}, error={error}")
        if not success:
            raise RuntimeError(error)
        return True, None
    except Exception as e:
        logger.error(f"Error validating/loading model {model_id} for agent {agent}: {e}")
        return False, str(e)


# Refactor _worker
# Example: Delegate preload job tasks to the preload module
def _worker(selected_agents: Optional[List[str]], strict_override: Optional[bool]) -> Dict[str, Any]:
	logger.info("Starting model preload worker")
	try:
		model_map = _read_agent_model_map()
		agents = selected_agents or list(model_map.keys())
		# Prepare status entries
		for a in agents:
			models = model_map.get(a, [])
			_MODEL_PRELOAD_STATE["per_agent"][a] = {}
			for mid in models:
				_MODEL_PRELOAD_STATE["per_agent"][a][mid] = {"status": "pending", "error": None, "duration_s": None}
		total = sum(len(model_map.get(a, [])) for a in agents)
		_MODEL_PRELOAD_STATE["summary"]["total"] = total

		strict_env = os.environ.get("STRICT_MODEL_STORE", "0").lower() in ("1", "true", "yes")
		strict = strict_override if strict_override is not None else strict_env

		logger.debug(f"Initial _MODEL_PRELOAD_STATE: {_MODEL_PRELOAD_STATE}")

		# Iterate and preload each model on CPU
		for a in agents:
			for mid in model_map.get(a, []):
				st = _MODEL_PRELOAD_STATE["per_agent"][a][mid]
				logger.debug(f"Processing model {mid} for agent {a}")
				logger.debug(f"Before invoking _validate_and_load_model: {st}")
				logger.debug(f"_MODEL_PRELOAD_STATE summary before: {_MODEL_PRELOAD_STATE['summary']}")
				st["status"] = "loading"
				t0 = time.time()
				ok, err = _validate_and_load_model(a, mid, strict)
				logger.debug(f"_validate_and_load_model result: ok={ok}, err={err}")
				if ok:
					st["status"] = "ok"
					st["duration_s"] = time.time() - t0
					_MODEL_PRELOAD_STATE["summary"]["done"] += 1
				else:
					st["status"] = "error"
					st["error"] = err
					st["duration_s"] = time.time() - t0
					_MODEL_PRELOAD_STATE["summary"]["failed"] += 1
				logger.debug(f"Updated _MODEL_PRELOAD_STATE for agent {a}, model {mid}: {st}")
				logger.debug(f"_MODEL_PRELOAD_STATE summary after: {_MODEL_PRELOAD_STATE['summary']}")
			logger.debug(f"_MODEL_PRELOAD_STATE after processing agent {a}: {_MODEL_PRELOAD_STATE}")
	except Exception as e:  # noqa: BLE001
		logger.error(f"Model preload worker crashed: {e}")
	finally:
		_MODEL_PRELOAD_STATE["in_progress"] = False
		_MODEL_PRELOAD_STATE["completed_at"] = time.time()
		logger.debug(f"Final _MODEL_PRELOAD_STATE: {_MODEL_PRELOAD_STATE}")


@app.post("/models/preload")
def models_preload(req: PreloadRequest):
	"""Start a background model preload job (CPU warming) using AGENT_MODEL_MAP.json.

	Returns current job state. If a job is already completed and refresh=false, returns that state.
	"""
	# If job completed and not refreshing, return existing state.
	# If there were failures, return 503 to enforce a hard failure with clear reasons.
	if _MODEL_PRELOAD_STATE.get("started_at") and not _MODEL_PRELOAD_STATE.get("in_progress") and not req.refresh:
		failed = int(_MODEL_PRELOAD_STATE.get("summary", {}).get("failed", 0) or 0)
		all_ready = (failed == 0 and _MODEL_PRELOAD_STATE["summary"].get("done", 0) == _MODEL_PRELOAD_STATE["summary"].get("total", 0))
		state = {**_MODEL_PRELOAD_STATE, "all_ready": all_ready}
		# Build a concise error list for clarity
		errors: List[Dict[str, Any]] = []
		for a, models in _MODEL_PRELOAD_STATE.get("per_agent", {}).items():
			for mid, st in models.items():
				if st.get("status") == "error":
					errors.append({"agent": a, "model": mid, "error": st.get("error")})
		state["errors"] = errors
		if failed > 0:
			raise HTTPException(status_code=503, detail=state)
		return state

	state = start_preload_job(req.agents, req.strict)
	logger.debug(f"_MODEL_PRELOAD_STATE during /models/preload: {_MODEL_PRELOAD_STATE}")
	logger.debug(f"_MODEL_PRELOAD_STATE before response: {_MODEL_PRELOAD_STATE}")
	return {
		**state,
		"all_ready": False,
	}


@app.get("/mps/allocation")
def get_mps_allocation():
	"""Return MPS resource allocation configuration for all agents."""
	try:
		import json
		from pathlib import Path
		
		project_root = Path(__file__).resolve().parents[2]
		config_path = project_root / "config" / "gpu" / "mps_allocation_config.json"
		
		if not config_path.exists():
			return {"error": "MPS allocation configuration not found", "path": str(config_path)}
		
		with open(config_path, "r") as f:
			config = json.load(f)
		
		return config
	except Exception as e:
		logger.error(f"Failed to load MPS allocation config: {e}")
		return {"error": str(e)}


@app.get("/models/status")
def models_status():
	"""Return current model preload status."""
	failed = int(get_preload_status().get("summary", {}).get("failed", 0) or 0)
	done = int(get_preload_status().get("summary", {}).get("done", 0) or 0)
	total = int(get_preload_status().get("summary", {}).get("total", 0) or 0)
	
	all_ready = (failed == 0 and done == total and not get_preload_status().get("in_progress", False))
	
	# Build error list for failed models
	errors = []
	if get_preload_status().get("per_agent"):
		for agent, models in get_preload_status()["per_agent"].items():
			for model_id, status in models.items():
				if status.get("status") == "error":
					errors.append({
						"agent": agent,
						"model": model_id,
						"error": status.get("error")
					})
	
	return {
		"all_ready": all_ready,
		"in_progress": get_preload_status().get("in_progress", False),
		"summary": get_preload_status().get("summary", {}),
		"errors": errors,
		"started_at": get_preload_status().get("started_at"),
		"completed_at": get_preload_status().get("completed_at"),
	}


@app.get("/tools")
def list_tools():
    """List all tools exposed by the GPU Orchestrator."""
    return {"tools": [
        "health",
        "gpu_info",
        "get_policy",
        "set_policy",
        "get_allocations",
        "lease",
        "release",
        "models_preload",
        "models_status",
        "mps_allocation"
    ]}


@app.post("/notify_ready")
def notify_ready():
    """Handle notification from MCP Bus that it is ready."""
    try:
        client = MCPBusClient()
        client.register_agent(
            agent_name="gpu_orchestrator",
            agent_address=f"http://localhost:{GPU_ORCHESTRATOR_PORT}",
            tools=[
                "health",
                "gpu_info",
                "get_policy",
                "set_policy",
                "get_allocations",
                "lease",
                "release",
                "models_preload",
                "models_status",
                "mps_allocation",
            ],
        )
        logger.info("Successfully registered GPU Orchestrator with MCP Bus after notification.")
    except Exception as e:
        logger.error(f"Failed to register GPU Orchestrator with MCP Bus: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@app.on_event("startup")
async def orchestrator_startup():
    logger.info("Starting GPU Orchestrator...")
    initialize_nvml()  # Explicitly call the NVML initialization function
    logger.info("GPU Orchestrator startup sequence complete.")


@app.on_event("startup")
def initialize_nvml():
    global _NVML_SUPPORTED, _NVML_INIT_ERROR
    logger.debug("Checking ENABLE_NVML environment variable...")
    enable_nvml = os.environ.get("ENABLE_NVML", "false").lower() == "true"
    logger.debug(f"ENABLE_NVML is set to: {enable_nvml}")

    if not enable_nvml:
        logger.info("NVML is disabled via environment variable.")
        return

    logger.debug("Attempting to initialize NVML during startup...")
    try:
        import pynvml  # type: ignore
        pynvml.nvmlInit()
        _NVML_SUPPORTED = True
        logger.debug("NVML initialized successfully during startup.")

        # Log detailed GPU information
        device_count = pynvml.nvmlDeviceGetCount()
        logger.debug(f"Number of devices detected: {device_count}")
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            logger.debug(f"Device {i}: {name.decode('utf-8')}")
            logger.debug(f"  Total memory: {memory_info.total / 1024**2} MB")
            logger.debug(f"  Used memory: {memory_info.used / 1024**2} MB")
            logger.debug(f"  Free memory: {memory_info.free / 1024**2} MB")
    except Exception as e:
        _NVML_SUPPORTED = False
        _NVML_INIT_ERROR = str(e)
        logger.error(f"NVML initialization failed during startup: {e}")


if __name__ == "__main__":
	import uvicorn

	# Place the runner at the very end so all endpoints above are registered
	uvicorn.run(app, host="0.0.0.0", port=GPU_ORCHESTRATOR_PORT)

