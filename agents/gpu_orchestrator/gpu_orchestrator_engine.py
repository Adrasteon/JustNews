"""
GPU Orchestrator Engine - Core logic for GPU management and model preloading.

This module contains the sophisticated GPU orchestration functionality including:
- NVML integration for detailed GPU monitoring
- Model preloading with background job management
- GPU lease allocation and management
- MPS (Multi-Process Service) detection and configuration
- Comprehensive telemetry and health monitoring
"""

import os
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pynvml  # type: ignore
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from common.metrics import JustNewsMetrics
from prometheus_client import Counter, Gauge

# Constants
GPU_ORCHESTRATOR_PORT = int(os.environ.get("GPU_ORCHESTRATOR_PORT", "8008"))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
SAFE_MODE = os.environ.get("SAFE_MODE", "false").lower() == "true"
ENABLE_NVML = os.environ.get("ENABLE_NVML", "false").lower() == "true"

# Global state
_START_TIME = time.time()
READINESS = False
POLICY = {
    "max_memory_per_agent_mb": 4096,
    "allow_fractional_shares": False,
    "kill_on_oom": False,
}
ALLOCATIONS: Dict[str, Dict[str, Any]] = {}
_MODEL_PRELOAD_STATE = {
    "started_at": None,
    "completed_at": None,
    "in_progress": False,
    "summary": {"total": 0, "done": 0, "failed": 0},
    "per_agent": {},
}

# NVML state
_NVML_SUPPORTED = False
_NVML_INIT_ERROR: Optional[str] = None
_NVML_HANDLE_CACHE: Dict[int, Any] = {}


class GPUOrchestratorEngine:
    """Core engine for GPU orchestration and management."""

    def __init__(self):
        self.logger = self._setup_logging()
        self.metrics = JustNewsMetrics("gpu_orchestrator")
        self._initialize_metrics()

    def _setup_logging(self):
        """Set up logging for the GPU orchestrator."""
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(__name__)

    def _initialize_metrics(self):
        """Initialize Prometheus metrics."""
        # Uptime gauge
        self.uptime_gauge = Gauge(
            'gpu_orchestrator_uptime_seconds',
            'GPU orchestrator uptime in seconds',
            ['agent', 'agent_display_name'],
            registry=self.metrics.registry
        )
        self.uptime_gauge.labels(
            agent=self.metrics.agent_name,
            agent_display_name=self.metrics.display_name
        ).set(time.time() - _START_TIME)

        # MPS enabled gauge
        self.mps_enabled_gauge = Gauge(
            'gpu_orchestrator_mps_enabled',
            'Whether NVIDIA MPS is enabled (1) or disabled (0)',
            ['agent', 'agent_display_name'],
            registry=self.metrics.registry
        )

        # Lease expired counter
        self.lease_expired_counter = Counter(
            'gpu_orchestrator_lease_expired_total',
            'Total number of GPU leases that have expired',
            ['agent', 'agent_display_name'],
            registry=self.metrics.registry
        )

        # NVML supported gauge
        self.nvml_supported_gauge = Gauge(
            'gpu_orchestrator_nvml_supported',
            'Whether NVML is supported and enabled (1) or not (0)',
            ['agent', 'agent_display_name'],
            registry=self.metrics.registry
        )

    def initialize_nvml(self) -> None:
        """Initialize NVML for GPU monitoring."""
        global _NVML_SUPPORTED, _NVML_INIT_ERROR

        if not ENABLE_NVML:
            self.logger.info("NVML is disabled via environment variable.")
            return

        try:
            pynvml.nvmlInit()
            _NVML_SUPPORTED = True
            self.logger.debug("NVML initialized successfully.")

            # Populate handle cache
            device_count = pynvml.nvmlDeviceGetCount()
            for i in range(device_count):
                _NVML_HANDLE_CACHE[i] = pynvml.nvmlDeviceGetHandleByIndex(i)

            # Log detailed GPU information
            for i in range(device_count):
                handle = _NVML_HANDLE_CACHE[i]
                name = pynvml.nvmlDeviceGetName(handle)
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                self.logger.debug(f"Device {i}: {name.decode('utf-8')}")
                self.logger.debug(f"  Total memory: {memory_info.total / 1024**2} MB")
                self.logger.debug(f"  Used memory: {memory_info.used / 1024**2} MB")
                self.logger.debug(f"  Free memory: {memory_info.free / 1024**2} MB")

        except Exception as e:
            _NVML_SUPPORTED = False
            _NVML_INIT_ERROR = str(e)
            self.logger.error(f"NVML initialization failed: {e}")

    def get_nvml_handle(self, index: int) -> Optional[Any]:
        """Get NVML handle for a GPU index."""
        return _NVML_HANDLE_CACHE.get(index)

    def _run_nvidia_smi(self) -> Optional[str]:
        """Run nvidia-smi and return CSV output."""
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ]
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=3)
            return output
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.debug(f"nvidia-smi unavailable or failed: {e}")
            return None

    def _parse_nvidia_smi_csv(self, csv_text: str) -> List[Dict[str, Any]]:
        """Parse nvidia-smi CSV output into GPU info dicts."""
        gpus: List[Dict[str, Any]] = []
        for line in csv_text.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue
            try:
                gpus.append({
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
                })
            except ValueError:
                continue
        return gpus

    def _get_nvml_enrichment(self, gpus: List[Dict[str, Any]]) -> None:
        """Enrich GPU info with NVML data."""
        if not ENABLE_NVML or SAFE_MODE or not _NVML_SUPPORTED:
            return

        try:
            for g in gpus:
                idx = g.get("index")
                if idx is not None:
                    try:
                        handle = self.get_nvml_handle(idx)
                        if handle:
                            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                            g["nvml_gpu_util_pct"] = getattr(util, "gpu", None)
                            g["nvml_mem_used_mb"] = round(mem.used / 1024**2, 2)
                            g["nvml_mem_total_mb"] = round(mem.total / 1024**2, 2)
                            g["nvml_mem_util_pct"] = round((mem.used / mem.total * 100.0) if mem.total else 0.0, 2)
                    except Exception as e:
                        g["nvml_error"] = str(e)
        except Exception as e:
            self.logger.warning(f"NVML enrichment error: {e}")

    def get_gpu_snapshot(self) -> Dict[str, Any]:
        """Return a conservative, read-only snapshot of GPU state."""
        smi = self._run_nvidia_smi()
        if smi is None:
            return {"gpus": [], "available": False, "message": "nvidia-smi not available"}

        gpus = self._parse_nvidia_smi_csv(smi)
        self._get_nvml_enrichment(gpus)

        return {
            "gpus": gpus,
            "available": True,
            "nvml_enriched": bool(ENABLE_NVML and not SAFE_MODE and _NVML_SUPPORTED),
            "nvml_supported": _NVML_SUPPORTED
        }

    def _detect_mps(self) -> Dict[str, Any]:
        """Detect NVIDIA MPS status."""
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
        return {
            "enabled": bool(enabled),
            "pipe_dir": pipe_dir,
            "control_process": bool(control_process)
        }

    def get_comprehensive_gpu_info(self) -> Dict[str, Any]:
        """Get comprehensive GPU information including MPS status."""
        data = self.get_gpu_snapshot()
        mps = self._detect_mps()
        data["mps_enabled"] = bool(mps.get("enabled", False))
        data["mps"] = mps

        # Update MPS metrics
        self.mps_enabled_gauge.labels(
            agent=self.metrics.agent_name,
            agent_display_name=self.metrics.display_name
        ).set(1 if data["mps_enabled"] else 0)

        return data

    def _purge_expired_leases(self) -> None:
        """Remove expired GPU leases."""
        now = time.time()
        expired = []
        for token, alloc in ALLOCATIONS.items():
            if now - alloc.get("timestamp", 0) > 3600:  # 1 hour TTL
                expired.append(token)

        for token in expired:
            ALLOCATIONS.pop(token, None)

        if expired:
            self.lease_expired_counter.labels(
                agent=self.metrics.agent_name,
                agent_display_name=self.metrics.display_name
            ).inc(len(expired))

    def _validate_lease_request(self, req: Dict[str, Any]) -> Optional[str]:
        """Validate lease request parameters."""
        if req.get("min_memory_mb") is not None and req["min_memory_mb"] < 0:
            return "min_memory_mb must be >= 0"
        return None

    def _allocate_gpu(self, req: Dict[str, Any]) -> Tuple[bool, Optional[int]]:
        """Allocate GPU based on request."""
        snapshot = self.get_gpu_snapshot()
        if not snapshot.get("available") or not snapshot.get("gpus"):
            return False, None

        candidates = []
        for g in snapshot["gpus"]:
            if req.get("min_memory_mb") and (g["memory_total_mb"] - g["memory_used_mb"]) < req["min_memory_mb"]:
                continue
            candidates.append(g)

        if candidates:
            return True, sorted(candidates, key=lambda x: x["memory_used_mb"])[0]["index"]
        return False, None

    def lease_gpu(self, agent: str, min_memory_mb: Optional[int] = 0) -> Dict[str, Any]:
        """Obtain a GPU lease."""
        self._purge_expired_leases()

        if SAFE_MODE:
            return {"granted": False, "note": "SAFE_MODE", "agent": agent}

        req = {"agent": agent, "min_memory_mb": min_memory_mb}
        err = self._validate_lease_request(req)
        if err:
            raise HTTPException(status_code=400, detail=err)

        success, gpu_index = self._allocate_gpu(req)
        token = str(uuid.uuid4())
        allocation = {
            "agent": agent,
            "gpu": gpu_index if success else "cpu",
            "token": token,
            "timestamp": time.time(),
        }
        ALLOCATIONS[token] = allocation
        return {"granted": True, **allocation}

    def release_gpu_lease(self, token: str) -> Dict[str, Any]:
        """Release a GPU lease."""
        self._purge_expired_leases()
        alloc = ALLOCATIONS.pop(token, None)
        if not alloc:
            raise HTTPException(status_code=404, detail="unknown_token")
        return {"released": True, "token": token}

    def get_allocations(self) -> Dict[str, Any]:
        """Get current allocations."""
        self._purge_expired_leases()
        return {"allocations": ALLOCATIONS}

    def update_policy(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Update GPU policy."""
        if SAFE_MODE:
            return {**POLICY, "note": "SAFE_MODE enabled: policy updates accepted but not enacted"}

        changed = False
        if "max_memory_per_agent_mb" in update:
            POLICY["max_memory_per_agent_mb"] = int(update["max_memory_per_agent_mb"])
            changed = True
        if "allow_fractional_shares" in update:
            POLICY["allow_fractional_shares"] = bool(update["allow_fractional_shares"])
            changed = True
        if "kill_on_oom" in update:
            POLICY["kill_on_oom"] = bool(update["kill_on_oom"])
            changed = True

        if changed:
            self.logger.info(f"Updated GPU policy: {POLICY}")
        return POLICY

    def get_policy(self) -> Dict[str, Any]:
        """Get current policy."""
        return POLICY

    # Model preloading functionality
    def _project_root(self) -> str:
        """Get project root directory."""
        try:
            return str(Path(__file__).resolve().parents[2])
        except Exception:
            return os.getcwd()

    def _read_agent_model_map(self) -> Dict[str, Any]:
        """Read agent model map from JSON file."""
        try:
            project_root = Path(self._project_root())
            model_map_path = project_root / "AGENT_MODEL_MAP.json"

            if not model_map_path.exists():
                self.logger.warning(f"Model map file not found: {model_map_path}")
                return {}

            import json
            with open(model_map_path, "r") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to read agent model map: {e}")
            return {}

    def _validate_and_load_model(self, agent: str, model_id: str, strict: bool) -> Tuple[bool, Optional[str]]:
        """Validate and load a model."""
        try:
            from agents.common.model_loader import load_sentence_transformer
            self.logger.info(f"Validating and loading model {model_id} for agent {agent} (strict={strict})")
            load_sentence_transformer(model_id, agent=agent)
            return True, None
        except Exception as e:
            self.logger.error(f"Error validating/loading model {model_id} for agent {agent}: {e}")
            return False, str(e)

    def _preload_worker(self, selected_agents: Optional[List[str]], strict_override: Optional[bool]) -> None:
        """Background worker for model preloading."""
        try:
            model_map = self._read_agent_model_map()
            agents = selected_agents or list(model_map.keys())

            # Initialize status entries
            for a in agents:
                models = model_map.get(a, [])
                _MODEL_PRELOAD_STATE["per_agent"][a] = {}
                for mid in models:
                    _MODEL_PRELOAD_STATE["per_agent"][a][mid] = {
                        "status": "pending",
                        "error": None,
                        "duration_s": None
                    }

            total = sum(len(model_map.get(a, [])) for a in agents)
            _MODEL_PRELOAD_STATE["summary"]["total"] = total

            strict_env = os.environ.get("STRICT_MODEL_STORE", "0").lower() in ("1", "true", "yes")
            strict = strict_override if strict_override is not None else strict_env

            # Preload models
            for a in agents:
                for mid in model_map.get(a, []):
                    st = _MODEL_PRELOAD_STATE["per_agent"][a][mid]
                    st["status"] = "loading"
                    t0 = time.time()
                    ok, err = self._validate_and_load_model(a, mid, strict)
                    if ok:
                        st["status"] = "ok"
                        st["duration_s"] = time.time() - t0
                        _MODEL_PRELOAD_STATE["summary"]["done"] += 1
                    else:
                        st["status"] = "error"
                        st["error"] = err
                        st["duration_s"] = time.time() - t0
                        _MODEL_PRELOAD_STATE["summary"]["failed"] += 1

        except Exception as e:
            self.logger.error(f"Model preload worker crashed: {e}")
        finally:
            _MODEL_PRELOAD_STATE["in_progress"] = False
            _MODEL_PRELOAD_STATE["completed_at"] = time.time()

    def start_model_preload(self, agents: Optional[List[str]] = None,
                          refresh: bool = False, strict: Optional[bool] = None) -> Dict[str, Any]:
        """Start model preload job."""
        # Check if job already completed and not refreshing
        if (_MODEL_PRELOAD_STATE.get("started_at") and
            not _MODEL_PRELOAD_STATE.get("in_progress") and not refresh):

            failed = _MODEL_PRELOAD_STATE.get("summary", {}).get("failed", 0)
            all_ready = (failed == 0 and
                        _MODEL_PRELOAD_STATE["summary"].get("done", 0) ==
                        _MODEL_PRELOAD_STATE["summary"].get("total", 0))

            state = {**_MODEL_PRELOAD_STATE, "all_ready": all_ready}

            # Build error list
            errors = []
            for a, models in _MODEL_PRELOAD_STATE.get("per_agent", {}).items():
                for mid, st in models.items():
                    if st.get("status") == "error":
                        errors.append({"agent": a, "model": mid, "error": st.get("error")})
            state["errors"] = errors

            if failed > 0:
                raise HTTPException(status_code=503, detail=state)
            return state

        # Start new preload job
        _MODEL_PRELOAD_STATE["started_at"] = time.time()
        _MODEL_PRELOAD_STATE["in_progress"] = True
        _MODEL_PRELOAD_STATE["completed_at"] = None

        # Reset summary for new job
        _MODEL_PRELOAD_STATE["summary"] = {"total": 0, "done": 0, "failed": 0}

        thread = threading.Thread(
            target=self._preload_worker,
            args=(agents, strict),
            daemon=True
        )
        thread.start()

        return {**_MODEL_PRELOAD_STATE, "all_ready": False}

    def get_model_preload_status(self) -> Dict[str, Any]:
        """Get model preload status."""
        failed = _MODEL_PRELOAD_STATE.get("summary", {}).get("failed", 0)
        done = _MODEL_PRELOAD_STATE.get("summary", {}).get("done", 0)
        total = _MODEL_PRELOAD_STATE.get("summary", {}).get("total", 0)

        all_ready = (failed == 0 and done == total and not _MODEL_PRELOAD_STATE.get("in_progress", False))

        # Build error list
        errors = []
        if _MODEL_PRELOAD_STATE.get("per_agent"):
            for agent, models in _MODEL_PRELOAD_STATE["per_agent"].items():
                for model_id, status in models.items():
                    if status.get("status") == "error":
                        errors.append({
                            "agent": agent,
                            "model": model_id,
                            "error": status.get("error")
                        })

        return {
            "all_ready": all_ready,
            "in_progress": _MODEL_PRELOAD_STATE.get("in_progress", False),
            "summary": _MODEL_PRELOAD_STATE.get("summary", {}),
            "errors": errors,
            "started_at": _MODEL_PRELOAD_STATE.get("started_at"),
            "completed_at": _MODEL_PRELOAD_STATE.get("completed_at"),
        }

    def get_mps_allocation_config(self) -> Dict[str, Any]:
        """Get MPS allocation configuration."""
        try:
            import json
            project_root = Path(self._project_root())
            config_path = project_root / "config" / "gpu" / "mps_allocation_config.json"

            if not config_path.exists():
                return {"error": "MPS allocation configuration not found", "path": str(config_path)}

            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load MPS allocation config: {e}")
            return {"error": str(e)}

    def get_metrics_text(self) -> str:
        """Get Prometheus metrics as text."""
        from prometheus_client import generate_latest
        return generate_latest(self.metrics.registry).decode('utf-8')


# Global engine instance
engine = GPUOrchestratorEngine()