"""
GPU Orchestrator Engine - Core logic for GPU management and model preloading.

This module contains the sophisticated GPU orchestration functionality including:
- NVML integration for detailed GPU monitoring
- Model preloading with background job management
- GPU lease allocation and management
- MPS (Multi-Process Service) detection and configuration
- Comprehensive telemetry and health monitoring

Integration note:
 - For automatic telemetry capture when a GPU is active, this repo includes
     `scripts/perf/gpu_activity_agent.py` and `scripts/perf/gpu_telemetry_exporter.py`.
     See `docs/gpu_telemetry_integration.md` for recommended deployment and systemd examples.
"""

import json
import multiprocessing as mp
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

try:  # NVML bindings became optional once we moved to the conda-provided nvidia-ml-py package
    import pynvml  # type: ignore
    _HAS_PYNVML = True
except ModuleNotFoundError:  # pragma: no cover - exercised implicitly when NVML bindings are absent
    pynvml = None  # type: ignore
    _HAS_PYNVML = False
from fastapi import HTTPException
from prometheus_client import Counter, Gauge

from common.metrics import JustNewsMetrics
from database.utils.migrated_database_utils import create_database_service

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
ALLOCATIONS: dict[str, dict[str, Any]] = {}
_MODEL_PRELOAD_STATE = {
    "started_at": None,
    "completed_at": None,
    "in_progress": False,
    "summary": {"total": 0, "done": 0, "failed": 0},
    "per_agent": {},
}

# NVML state
_NVML_SUPPORTED = False
_NVML_INIT_ERROR: str | None = None
_NVML_HANDLE_CACHE: dict[int, Any] = {}


class GPUOrchestratorEngine:
    """Core engine for GPU orchestration and management."""

    def __init__(self):
        self.logger = self._setup_logging()
        self.metrics = JustNewsMetrics("gpu_orchestrator")
        self._initialize_metrics()
        # Start background lifecycle enforcer thread
        try:
            t = threading.Thread(target=self._background_policy_enforcer, daemon=True)
            t.start()
            self.logger.debug('Worker pool lifecycle enforcer started')
        except Exception as e:
            self.logger.warning(f'Failed to start lifecycle enforcer: {e}')
        # Worker pool management: track spawned adapter worker pools
        # Structure: {pool_id: {"model": str, "adapter": str|None, "num_workers": int, "procs": [Process], "started_at": float}}
        self._WORKER_POOLS: dict[str, dict] = {}
        # Optional MariaDB service used for persistence of leases and pools
        try:
            self.db_service = create_database_service()
        except Exception:
            self.db_service = None
        # Optional Redis client for streams
        try:
            import redis
            redis_url = os.environ.get('REDIS_URL', None)
            if redis_url:
                self.redis_client = redis.from_url(redis_url)
            else:
                # default localhost
                self.redis_client = redis.Redis()
        except Exception:
            self.redis_client = None

            # Reclaim / DLQ configuration
            self._job_retry_max = int(os.environ.get('ORCH_JOB_RETRY_MAX', '5'))
            self._claim_idle_ms = int(os.environ.get('ORCH_CLAIM_IDLE_MS', str(60 * 1000)))
            self._reclaim_interval_s = int(os.environ.get('ORCH_RECLAIM_INTERVAL_S', '30'))

            # Start background reclaimer loop if redis available
            try:
                if self.redis_client:
                    t = threading.Thread(target=self._reclaimer_loop, daemon=True)
                    t.start()
            except Exception:
                self.logger.debug('Failed to start reclaimer loop')
        # Rehydrate any persisted worker pool records so state survives restarts
        try:
            if self.db_service:
                self._rehydrate_worker_pools_from_db()
        except Exception:
            # Best-effort: continue with empty in-memory pools if DB read fails
            self.logger.debug('Failed to rehydrate worker pools from DB (continuing)')
        
        # Leader election state
        self._leader_lock_name = os.environ.get('GPU_ORCHESTRATOR_LEADER_LOCK', 'gpu_orchestrator_leader')
        # How long to wait for GET_LOCK when trying to acquire (seconds)
        self._leader_try_timeout = int(os.environ.get('GPU_ORCHESTRATOR_LEADER_TRY_TIMEOUT', '1'))
        self.is_leader = False

        # Start background election loop
        try:
            t = threading.Thread(target=self._leader_election_loop, daemon=True)
            t.start()
        except Exception:
            self.logger.debug('Failed to start leader election loop')

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

        # Worker pool metrics
        self.worker_pools_gauge = Gauge(
            'gpu_orchestrator_worker_pools_total',
            'Number of active worker pools',
            ['agent', 'agent_display_name'],
            registry=self.metrics.registry
        )

        self.worker_pool_workers_gauge = Gauge(
            'gpu_orchestrator_worker_pool_workers',
            'Number of workers in a pool',
            ['pool_id'],
            registry=self.metrics.registry
        )

        self.worker_pool_running_workers_gauge = Gauge(
            'gpu_orchestrator_worker_pool_running_workers',
            'Number of running worker processes in a pool',
            ['pool_id'],
            registry=self.metrics.registry
        )

        self.worker_pool_started_timestamp = Gauge(
            'gpu_orchestrator_worker_pool_started_ts',
            'Start timestamp of a worker pool (epoch seconds)',
            ['pool_id'],
            registry=self.metrics.registry
        )

        self.worker_pool_evictions_counter = Counter(
            'gpu_orchestrator_worker_pool_evictions_total',
            'Total number of pool evictions performed by lifecycle manager',
            ['reason'],
            registry=self.metrics.registry
        )

    def initialize_nvml(self) -> None:
        """Initialize NVML for GPU monitoring."""
        global _NVML_SUPPORTED, _NVML_INIT_ERROR

        if not ENABLE_NVML:
            self.logger.info("NVML is disabled via environment variable.")
            return

        if not _HAS_PYNVML:
            _NVML_SUPPORTED = False
            _NVML_INIT_ERROR = "pynvml module not available"
            self.logger.info("NVML requested but pynvml is not installed. Install nvidia-ml-py to enable NVML metrics.")
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

    def get_nvml_handle(self, index: int) -> Any | None:
        """Get NVML handle for a GPU index."""
        return _NVML_HANDLE_CACHE.get(index)

    def _run_nvidia_smi(self) -> str | None:
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

    def _parse_nvidia_smi_csv(self, csv_text: str) -> list[dict[str, Any]]:
        """Parse nvidia-smi CSV output into GPU info dicts."""
        gpus: list[dict[str, Any]] = []
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

    def _get_nvml_enrichment(self, gpus: list[dict[str, Any]]) -> None:
        """Enrich GPU info with NVML data."""
        if not ENABLE_NVML or SAFE_MODE or not _NVML_SUPPORTED or not _HAS_PYNVML:
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

    def get_gpu_snapshot(self) -> dict[str, Any]:
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

    def _detect_mps(self) -> dict[str, Any]:
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

    def get_comprehensive_gpu_info(self) -> dict[str, Any]:
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

        # Also purge expired leases from persistent DB (best-effort)
        try:
            if self.db_service:
                cursor = self.db_service.mb_conn.cursor()
                cursor.execute("DELETE FROM orchestrator_leases WHERE expires_at IS NOT NULL AND expires_at < NOW()")
                self.db_service.mb_conn.commit()
                cursor.close()
        except Exception:
            # Non-fatal - leave in-memory cleanup as primary
            self.logger.debug("Failed to purge expired leases from DB (continuing)")

    def _validate_lease_request(self, req: dict[str, Any]) -> str | None:
        """Validate lease request parameters."""
        if req.get("min_memory_mb") is not None and req["min_memory_mb"] < 0:
            return "min_memory_mb must be >= 0"
        return None

    def _allocate_gpu(self, req: dict[str, Any]) -> tuple[bool, int | None]:
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

    def lease_gpu(self, agent: str, min_memory_mb: int | None = 0) -> dict[str, Any]:
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
        # Persist lease to DB (best-effort) with a default TTL (1h)
        try:
            if self.db_service:
                ttl = int(os.environ.get('GPU_ORCHESTRATOR_LEASE_TTL', '3600'))
                cursor = self.db_service.mb_conn.cursor()
                # Use FROM_UNIXTIME for created_at handling where helpful, but simple NOW()/DATE_ADD is fine
                cursor.execute(
                    "INSERT INTO orchestrator_leases (token, agent_name, gpu_index, mode, created_at, expires_at, last_heartbeat, metadata) VALUES (%s,%s,%s,%s,NOW(),DATE_ADD(NOW(), INTERVAL %s SECOND),NOW(),%s)",
                    (token, agent, gpu_index if success else None, 'gpu' if success else 'cpu', ttl, json.dumps(allocation))
                )
                self.db_service.mb_conn.commit()
                cursor.close()
        except Exception as e:
            self.logger.debug(f"Failed to persist lease to DB (non-fatal): {e}")
        return {"granted": True, **allocation}

    def release_gpu_lease(self, token: str) -> dict[str, Any]:
        """Release a GPU lease."""
        self._purge_expired_leases()
        alloc = ALLOCATIONS.pop(token, None)
        if not alloc:
            raise HTTPException(status_code=404, detail="unknown_token")
        # Also remove persistent lease row (best-effort)
        try:
            if self.db_service:
                cursor = self.db_service.mb_conn.cursor()
                cursor.execute("DELETE FROM orchestrator_leases WHERE token = %s", (token,))
                self.db_service.mb_conn.commit()
                cursor.close()
        except Exception:
            self.logger.debug("Failed to remove lease row from DB (non-fatal)")
        return {"released": True, "token": token}

    def heartbeat_lease(self, token: str) -> bool:
        """Update last_heartbeat for lease token in DB (best-effort)."""
        try:
            # Update in-memory timestamp if present
            if token in ALLOCATIONS:
                ALLOCATIONS[token]['timestamp'] = time.time()
            if self.db_service:
                cursor = self.db_service.mb_conn.cursor()
                cursor.execute("UPDATE orchestrator_leases SET last_heartbeat = NOW() WHERE token = %s", (token,))
                self.db_service.mb_conn.commit()
                cursor.close()
            return True
        except Exception as e:
            self.logger.debug(f"Failed to heartbeat lease in DB: {e}")
            return False

    def get_allocations(self) -> dict[str, Any]:
        """Get current allocations."""
        self._purge_expired_leases()
        return {"allocations": ALLOCATIONS}

    def update_policy(self, update: dict[str, Any]) -> dict[str, Any]:
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

    # Default pool lifecycle policy values (configurable via env or API)
    def _pool_policy_defaults(self):
        # Merge defaults from system configuration if available
        defaults = {
            'min_warm_workers_per_pool': int(os.environ.get('GPU_POOL_MIN_WARM', '0')),
            'max_total_workers': int(os.environ.get('GPU_POOL_MAX_TOTAL', '8')),
            'pool_idle_timeout_s': int(os.environ.get('GPU_POOL_IDLE_TIMEOUT_S', '300')),
            'enforce_period_s': int(os.environ.get('GPU_POOL_POLICY_PERIOD_S', '10')),
        }
        try:
            # runtime import of config module so tests can monkeypatch
            from config.core import get_gpu_config
            gconf = get_gpu_config()
            if gconf:
                defaults['min_warm_workers_per_pool'] = gconf.get('min_warm_workers_per_pool', defaults['min_warm_workers_per_pool'])
                defaults['max_total_workers'] = gconf.get('max_total_workers', defaults['max_total_workers'])
                defaults['pool_idle_timeout_s'] = gconf.get('pool_idle_timeout_s', defaults['pool_idle_timeout_s'])
                defaults['enforce_period_s'] = gconf.get('enforce_period_s', defaults['enforce_period_s'])
        except Exception:
            pass
        return defaults

    def get_pool_policy(self) -> dict[str, Any]:
        if not hasattr(self, '_POOL_POLICY'):
            self._POOL_POLICY = self._pool_policy_defaults()
        return self._POOL_POLICY

    def set_pool_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        cur = self.get_pool_policy()
        cur.update(policy)
        self._POOL_POLICY = cur
        # Trigger immediate enforcement so policy changes take effect promptly
        try:
            self._enforce_pool_policy_once()
        except Exception:
            pass

        return self._POOL_POLICY

    def _enforce_pool_policy_once(self) -> None:
        """Perform one enforcement pass (evict pools if over configured limits).

        This is a synchronous variant used to trigger immediate enforcement after
        policy updates or during tests/ops where waiting for the background
        enforcer is undesirable.
        """
        try:
            policy = self.get_pool_policy()
            total = sum(p.get('num_workers', 0) for p in self._WORKER_POOLS.values())
            max_total = policy.get('max_total_workers', 8)

            if total > max_total:
                ordered = sorted(self._WORKER_POOLS.items(), key=lambda kv: kv[1].get('started_at', 0))
                for pool_id, meta in ordered:
                    if total <= max_total:
                        break
                    try:
                        self.stop_worker_pool(pool_id)
                        total -= meta.get('num_workers', 0)
                        self.worker_pool_evictions_counter.labels(reason='over_total_sync').inc()
                    except Exception:
                        pass

                if total > max_total:
                    for pool_id, meta in ordered:
                        if total <= max_total:
                            break
                        try:
                            self.stop_worker_pool(pool_id)
                            total -= meta.get('num_workers', 0)
                            self.worker_pool_evictions_counter.labels(reason='over_total_force_sync').inc()
                        except Exception:
                            pass
        except Exception:
            pass

    def _background_policy_enforcer(self):
        """Background thread that enforces pool lifecycle policies periodically."""
        while True:
            try:
                # Only the leader should actively enforce pool lifecycle policies.
                if not getattr(self, 'is_leader', False):
                    # still update metrics snapshot but skip enforcement
                    self.worker_pools_gauge.labels(agent=self.metrics.agent_name, agent_display_name=self.metrics.display_name).set(len(self._WORKER_POOLS))
                    time.sleep(self.get_pool_policy().get('enforce_period_s', 10))
                    continue

                policy = self.get_pool_policy()
                self.logger.debug(f"Policy enforcer tick: policy={policy}")
                # Compute total configured workers
                total = sum(p.get('num_workers', 0) for p in self._WORKER_POOLS.values())
                self.logger.debug(f"Policy enforcer tick: current_total_workers={total}, pools={list(self._WORKER_POOLS.keys())}")
                max_total = policy.get('max_total_workers', 8)

                # Evict least-recently used pools if over max_total
                if total > max_total:
                    # sort by started_at ascending
                    ordered = sorted(self._WORKER_POOLS.items(), key=lambda kv: kv[1].get('started_at', 0))
                    evicted = 0
                    for pool_id, meta in ordered:
                        if total <= max_total:
                            break
                        # skip pools with min_warm requirement
                        min_warm = policy.get('min_warm_workers_per_pool', 0)
                        if meta.get('num_workers', 0) <= min_warm:
                            continue
                        # evict whole pool
                        try:
                            self.logger.info(f"Evicting worker pool {pool_id} to reduce total workers")
                            self.stop_worker_pool(pool_id)
                            total -= meta.get('num_workers', 0)
                            evicted += 1
                            self.worker_pool_evictions_counter.labels(reason='over_total').inc()
                        except Exception:
                            pass

                    # Fallback: if total still above threshold, evict pools regardless of min_warm to make progress
                    if total > max_total:
                        for pool_id, meta in ordered:
                            if total <= max_total:
                                break
                            try:
                                self.logger.info(f"Force-evicting worker pool {pool_id} to enforce limit")
                                self.stop_worker_pool(pool_id)
                                total -= meta.get('num_workers', 0)
                                self.worker_pool_evictions_counter.labels(reason='over_total_force').inc()
                            except Exception:
                                pass

                # Evict pools that have been idle longer than pool_idle_timeout_s
                now = time.time()
                idle_timeout = policy.get('pool_idle_timeout_s', 300)
                for pool_id, meta in list(self._WORKER_POOLS.items()):
                    started = meta.get('started_at', now)
                    running = sum(1 for p in meta.get('procs', []) if p.is_alive())
                    # if no running workers and older than timeout, evict
                    if running == 0 and (now - started) > idle_timeout:
                        try:
                            self.stop_worker_pool(pool_id)
                            self.worker_pool_evictions_counter.labels(reason='idle_timeout').inc()
                        except Exception:
                            pass

                # update metrics per pool
                self.worker_pools_gauge.labels(agent=self.metrics.agent_name, agent_display_name=self.metrics.display_name).set(len(self._WORKER_POOLS))
                for pid, meta in self._WORKER_POOLS.items():
                    self.worker_pool_workers_gauge.labels(pool_id=pid).set(meta.get('num_workers', 0))
                    running = sum(1 for p in meta.get('procs', []) if p.is_alive())
                    self.worker_pool_running_workers_gauge.labels(pool_id=pid).set(running)
                    if meta.get('started_at'):
                        self.worker_pool_started_timestamp.labels(pool_id=pid).set(meta.get('started_at'))

            except Exception:
                pass

            # Sleep until next enforcement
            period = self.get_pool_policy().get('enforce_period_s', 10)
            time.sleep(period)

    def try_acquire_leader_lock(self, timeout: int | None = None) -> bool:
        """Attempt to acquire a MariaDB GET_LOCK for leader role.

        Returns True if lock acquired and False otherwise.
        This is best-effort and uses the current db connection associated with the
        engine's `db_service`. If no DB is available or an error occurs, returns False.
        """
        if not self.db_service:
            return False
        try:
            if timeout is None:
                timeout = self._leader_try_timeout
            cursor = self.db_service.mb_conn.cursor()
            cursor.execute("SELECT GET_LOCK(%s,%s)", (self._leader_lock_name, int(timeout)))
            res = cursor.fetchone()
            cursor.close()
            locked = bool(res and int(res[0]) == 1)
            if locked:
                self.is_leader = True
                self.logger.info('Acquired leader lock')
            return locked
        except Exception as e:
            self.logger.debug(f'Leader lock attempt failed: {e}')
            return False

    def release_leader_lock(self) -> bool:
        """Release the MariaDB GET_LOCK if held.

        Returns True if the lock was released, False on failure.
        """
        if not self.db_service:
            return False
        try:
            cursor = self.db_service.mb_conn.cursor()
            cursor.execute("SELECT RELEASE_LOCK(%s)", (self._leader_lock_name,))
            res = cursor.fetchone()
            cursor.close()
            released = bool(res and res[0] == 1)
            if released:
                self.is_leader = False
                self.logger.info('Released leader lock')
            return released
        except Exception as e:
            self.logger.debug(f'Failed to release leader lock: {e}')
            return False

    def _leader_election_loop(self):
        """Background loop that acquires leadership when possible and yields when lost."""
        # If we don't have a DB connection, do nothing.
        while True:
            try:
                if not getattr(self, 'is_leader', False):
                    got = self.try_acquire_leader_lock(timeout=self._leader_try_timeout)
                    if got:
                        # When becoming leader, reconcile state immediately (best-effort)
                        try:
                            self._rehydrate_worker_pools_from_db()
                        except Exception:
                            pass
                else:
                    # we are leader; verify connection still healthy (best-effort)
                    try:
                        # a simple no-op query to detect dead connection
                        cursor = self.db_service.mb_conn.cursor()
                        cursor.execute('SELECT 1')
                        cursor.fetchone()
                        cursor.close()
                    except Exception:
                        # lost DB connection -> lose leadership
                        self.logger.warning('Leader DB connection lost, relinquishing leadership')
                        self.is_leader = False
                time.sleep(int(os.environ.get('GPU_ORCHESTRATOR_LEADER_LOOP_S', '2')))
            except Exception:
                # don't crash the loop
                time.sleep(2)


    def get_policy(self) -> dict[str, Any]:
        """Get current policy."""
        return POLICY

    # Model preloading functionality
    def _project_root(self) -> str:
        """Get project root directory."""
        try:
            return str(Path(__file__).resolve().parents[2])
        except Exception:
            return os.getcwd()

    def _read_agent_model_map(self) -> dict[str, Any]:
        """Read agent model map from JSON file."""
        try:
            project_root = Path(self._project_root())
            model_map_path = project_root / "AGENT_MODEL_MAP.json"

            if not model_map_path.exists():
                self.logger.warning(f"Model map file not found: {model_map_path}")
                return {}

            import json

            with open(model_map_path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            # Legacy structure: treat as agents dict
            return {"agents": data}
        except Exception as e:
            self.logger.error(f"Failed to read agent model map: {e}")
            return {}

    def _agents_section(self, model_map: dict[str, Any]) -> dict[str, Any]:
        agents_cfg = model_map.get("agents")
        if agents_cfg is not None and isinstance(agents_cfg, dict):
            return agents_cfg
        # Legacy fallback: treat top-level keys as agents except metadata keys
        legacy = {}
        for key, value in model_map.items():
            if key == "base_models":
                continue
            legacy[key] = value
        return legacy

    def _normalize_agent_entries(self, model_map: dict[str, Any], agent: str) -> list[dict[str, Any]]:
        agents_cfg = self._agents_section(model_map)
        raw_entries = agents_cfg.get(agent, [])
        if not isinstance(raw_entries, list):
            raw_entries = [raw_entries]
        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_entries):
            if isinstance(item, dict):
                spec = dict(item)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                spec = {
                    "type": item[0],
                    "legacy_model_id": item[1],
                }
            else:
                spec = {"legacy_model_id": item}
            spec.setdefault("id", spec.get("adapter_name") or spec.get("legacy_model_id") or f"{agent}-{idx}")
            normalized.append(spec)
        return normalized

    def _validate_and_load_model(self, agent: str, spec: dict[str, Any], strict: bool) -> tuple[bool, str | None]:
        """Validate and load a model entry for an agent."""
        try:
            if spec.get("base_ref"):
                from agents.common.model_loader import load_transformers_with_adapter

                adapter_name = spec.get("adapter_name")
                self.logger.info(
                    "Validating base model + adapter for agent %s (adapter=%s, strict=%s)",
                    agent,
                    adapter_name or spec.get("base_ref"),
                    strict,
                )
                load_transformers_with_adapter(agent, adapter_name=adapter_name)
                return True, None

            legacy_model_id = spec.get("legacy_model_id") or spec.get("model_id")
            if not legacy_model_id:
                raise ValueError("AGENT_MODEL_MAP entry is missing a model identifier")

            model_type = spec.get("type")
            if not model_type:
                model_type = "sentence-transformers" if str(legacy_model_id).startswith("sentence-transformers/") else "transformers"

            self.logger.info(
                "Validating and loading model %s (type=%s) for agent %s (strict=%s)",
                legacy_model_id,
                model_type,
                agent,
                strict,
            )
            if model_type == "sentence-transformers":
                from agents.common.model_loader import load_sentence_transformer

                load_sentence_transformer(legacy_model_id, agent=agent)
            else:
                from agents.common.model_loader import load_transformers_model

                load_transformers_model(legacy_model_id, agent=agent)
            return True, None
        except Exception as e:
            self.logger.error(f"Error validating/loading model entry for agent {agent}: {e}")
            return False, str(e)

    def _preload_worker(self, selected_agents: list[str] | None, strict_override: bool | None) -> None:
        """Background worker for model preloading."""
        try:
            model_map = self._read_agent_model_map()
            agents_cfg = self._agents_section(model_map)
            agents = selected_agents or list(agents_cfg.keys())

            agent_specs: dict[str, list[dict[str, Any]]] = {}
            for agent in agents:
                specs = self._normalize_agent_entries(model_map, agent)
                # Attach manifest/metadata for new-format entries (best-effort)
                enriched_specs: list[dict[str, Any]] = []
                for spec in specs:
                    if spec.get("base_ref"):
                        try:
                            from agents.common.model_loader import get_agent_model_metadata

                            meta = get_agent_model_metadata(agent, spec.get("adapter_name"))
                            if meta:
                                spec = {**spec, "_model_metadata": meta}
                                variant = self._select_variant_for_spec(spec)
                                if variant:
                                    spec["_selected_variant"] = variant
                                    spec["_variant_vram_mb"] = self._variant_vram_mb(spec, variant)
                        except Exception as exc:
                            self.logger.debug("Failed to collect model metadata for agent=%s: %s", agent, exc)
                    enriched_specs.append(spec)
                agent_specs[agent] = enriched_specs

            # Initialize status entries
            for a in agents:
                models = agent_specs.get(a, [])
                _MODEL_PRELOAD_STATE["per_agent"][a] = {}
                for spec in models:
                    entry_id = spec.get("id")
                    _MODEL_PRELOAD_STATE["per_agent"][a][entry_id] = {
                        "status": "pending",
                        "error": None,
                        "duration_s": None,
                        "variant": spec.get("_selected_variant"),
                        "approx_vram_mb": spec.get("_variant_vram_mb"),
                    }

            total = sum(len(agent_specs.get(a, [])) for a in agents)
            _MODEL_PRELOAD_STATE["summary"]["total"] = total

            strict_env = os.environ.get("STRICT_MODEL_STORE", "0").lower() in ("1", "true", "yes")
            strict = strict_override if strict_override is not None else strict_env

            # Preload models
            for a in agents:
                for spec in agent_specs.get(a, []):
                    entry_id = spec.get("id")
                    st = _MODEL_PRELOAD_STATE["per_agent"][a][entry_id]
                    st["status"] = "loading"
                    t0 = time.time()
                    ok, err = self._validate_and_load_model(a, spec, strict)
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

    def start_model_preload(self, agents: list[str] | None = None,
                          refresh: bool = False, strict: bool | None = None) -> dict[str, Any]:
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

    def get_model_preload_status(self) -> dict[str, Any]:
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

    def _allow_quantized_variants(self) -> bool:
        return os.environ.get("GPU_ALLOW_QUANTIZED", "1").lower() not in {"0", "false", "no"}

    def _select_variant_for_spec(self, spec: dict[str, Any]) -> str | None:
        if spec.get("_selected_variant"):
            return spec["_selected_variant"]
        if spec.get("variant_preference"):
            return spec["variant_preference"]
        metadata = spec.get("_model_metadata") or {}
        manifest = metadata.get("manifest") if isinstance(metadata, dict) else None
        if not manifest:
            return None
        if self._allow_quantized_variants():
            for variant in manifest.get("quantized_variants", []) or []:
                if variant.get("recommended"):
                    return variant.get("name")
            variants = manifest.get("quantized_variants") or []
            if variants:
                return variants[0].get("name")
        return "fp16"

    def _variant_vram_mb(self, spec: dict[str, Any], variant: str | None) -> float | None:
        metadata = spec.get("_model_metadata") or {}
        manifest = metadata.get("manifest") if isinstance(metadata, dict) else None
        if not manifest:
            return None
        if not variant or variant == "fp16":
            return manifest.get("approx_vram_mb")
        for candidate in manifest.get("quantized_variants", []) or []:
            if candidate.get("name") == variant:
                return candidate.get("approx_vram_mb")
        return manifest.get("approx_vram_mb")

    # --- Worker pool management -------------------------------------------------
    def start_agent_worker_pool(
        self,
        agent: str,
        adapter_name: str | None = None,
        *,
        pool_id: str | None = None,
        num_workers: int = 1,
        hold_seconds: int = 600,
        requestor: dict | None = None,
    ) -> dict[str, Any]:
        """Start a worker pool using AGENT_MODEL_MAP metadata."""
        try:
            from agents.common.model_loader import get_agent_model_metadata
        except Exception as exc:
            raise RuntimeError("model loader unavailable") from exc

        metadata = get_agent_model_metadata(agent, adapter_name)
        if not metadata:
            raise ValueError(f"Unknown model metadata for agent={agent}")

        version_dir = metadata.get("version_dir")
        base_info = metadata.get("base_info", {})
        model_ref = str(version_dir) if version_dir else base_info.get("hf_id")
        if not model_ref:
            raise ValueError(f"Missing base model reference for agent={agent}")

        adapter_path = metadata.get("adapter_path")
        entry = metadata.get("entry", {}) or {}
        spec = {**entry, "_model_metadata": metadata}
        variant = self._select_variant_for_spec(spec)

        resolved_pool_id = pool_id or f"{agent}-{adapter_name or 'base'}"
        adapter_str = str(adapter_path) if adapter_path else None
        return self.start_worker_pool(
            pool_id=resolved_pool_id,
            model_id=str(model_ref),
            adapter=adapter_str,
            num_workers=num_workers,
            hold_seconds=hold_seconds,
            requestor=requestor,
            variant=variant,
        )

    def _spawn_pool_worker(self, model_id: str | None, adapter: str | None, hold_seconds: int, variant: str | None = None):
        """Process entrypoint that loads base model and adapter then sleeps for hold_seconds.

        Note: in RE_RANKER_TEST_MODE this function will avoid heavy loads and simply sleep.
        """
        # Local import to avoid heavy deps at module import time in tests
        if os.environ.get('RE_RANKER_TEST_MODE', '1') in ('1', 'true'):
            # test mode: minimal work and hold
            time.sleep(hold_seconds)
            return

        try:
            import torch
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                BitsAndBytesConfig,
            )

            if variant == 'fp16':
                model = AutoModelForCausalLM.from_pretrained(
                    model_id,
                    dtype=getattr(torch, 'float16', None),
                    device_map='auto',
                )
            elif variant == 'bnb-4bit-qlora':
                bnb = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=getattr(torch, 'float16', None),
                    bnb_4bit_quant_type='nf4',
                )
                model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=bnb, device_map='auto')
            else:  # default to 8-bit
                bnb = BitsAndBytesConfig(
                    load_in_8bit=True,
                    bnb_8bit_use_double_quant=True,
                    bnb_8bit_compute_dtype=getattr(torch, 'float16', None),
                )
                model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=bnb, device_map='auto')
            _tok = AutoTokenizer.from_pretrained(model_id)

            if adapter:
                try:
                    from peft import PeftModel
                    model = PeftModel.from_pretrained(model, adapter)
                except Exception:
                    # adapter not available or failed – proceed
                    pass

            time.sleep(hold_seconds)

        except Exception:
            # Fail fast but keep process alive a short while so parent can introspect
            time.sleep(min(hold_seconds, 3))

    def start_worker_pool(
        self,
        pool_id: str,
        model_id: str | None,
        adapter: str | None,
        num_workers: int = 1,
        hold_seconds: int = 600,
        requestor: dict | None = None,
        variant: str | None = None,
    ) -> dict[str, Any]:
        """Start a named pool of warm workers for a given base model + adapter.

        This is intended for interactive dev/test and to allow GPU Orchestrator to
        keep a set of worker processes warm and ready. Pools are idempotent – attempting
        to start an already-running pool will return its existing state.
        """
        if pool_id in self._WORKER_POOLS:
            return {**self._WORKER_POOLS[pool_id], 'note': 'already_running'}

        # Validate args
        if num_workers < 1:
            raise ValueError('num_workers must be >= 1')

        procs: list[mp.Process] = []
        for _ in range(num_workers):
            p = mp.Process(target=self._spawn_pool_worker, args=(model_id, adapter, hold_seconds, variant), daemon=True)
            p.start()
            procs.append(p)
            time.sleep(0.2)

        self._WORKER_POOLS[pool_id] = {
            'model': model_id,
            'adapter': adapter,
            'num_workers': num_workers,
            'procs': procs,
            'started_at': time.time(),
            'hold_seconds': hold_seconds,
            'variant': variant,
        }

        # Audit with optional requestor
        self._audit_worker_pool_event('start', pool_id, model_id, adapter, num_workers, requestor=requestor, variant=variant)
        # Persist worker pool row to DB (best-effort)
        try:
            if self.db_service:
                cursor = self.db_service.mb_conn.cursor()
                cursor.execute(
                    "INSERT INTO worker_pools (pool_id, agent_name, model_id, adapter, desired_workers, spawned_workers, started_at, status, hold_seconds, metadata) VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s)",
                    (pool_id, requestor.get('user') if requestor else None, model_id, adapter, num_workers, num_workers, 'running', hold_seconds, json.dumps({'variant': variant}))
                )
                self.db_service.mb_conn.commit()
                cursor.close()
        except Exception:
            self.logger.debug('Failed to persist worker_pool to DB (non-fatal)')
        return {'pool_id': pool_id, 'num_workers': num_workers, 'status': 'started', 'variant': variant}

    def stop_worker_pool(self, pool_id: str) -> dict[str, Any]:
        """Terminate a previously started pool and reap processes."""
        pool = self._WORKER_POOLS.get(pool_id)
        if not pool:
            raise ValueError('unknown_pool')

        procs = pool.get('procs', [])
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        # wait join
        for p in procs:
            try:
                p.join(timeout=1.0)
            except Exception:
                pass

        self._WORKER_POOLS.pop(pool_id, None)
        self._audit_worker_pool_event('stop', pool_id, None, None, 0, requestor=None)
        # Mark persistent pool as stopped (best-effort)
        try:
            if self.db_service:
                cursor = self.db_service.mb_conn.cursor()
                cursor.execute("UPDATE worker_pools SET status=%s, spawned_workers=0 WHERE pool_id=%s", ('stopped', pool_id))
                self.db_service.mb_conn.commit()
                cursor.close()
        except Exception:
            self.logger.debug('Failed to update worker_pool status in DB (non-fatal)')
        return {'pool_id': pool_id, 'status': 'stopped'}

    def list_worker_pools(self) -> list[dict[str, Any]]:
        """Return summary of active pools."""
        out = []
        for pid, meta in list(self._WORKER_POOLS.items()):
            running = sum(1 for p in meta.get('procs', []) if p.is_alive())
            out.append({
                'pool_id': pid,
                'model': meta.get('model'),
                'adapter': meta.get('adapter'),
                'configured_workers': meta.get('num_workers'),
                'running_workers': running,
                'started_at': meta.get('started_at'),
                'variant': meta.get('variant'),
            })
        return out

    def hot_swap_pool_adapter(self, pool_id: str, new_adapter: str | None, requestor: dict | None = None, wait_seconds: int = 10) -> dict[str, Any]:
        """Hot-swap adapter for a named pool: start new workers with new adapter, then stop old workers.

        This performs a blue-green style swap to avoid downtime: it spawns the same
        number of new workers, waits for a short warm period, then terminates the old ones.
        """
        meta = self._WORKER_POOLS.get(pool_id)
        if not meta:
            raise ValueError('unknown_pool')

        num_workers = meta.get('num_workers', 1)
        model = meta.get('model')

        # Start a temporary replacement pool id
        _temp_id = f"{pool_id}__swap_{int(time.time())}"
        procs: list[mp.Process] = []
        for _ in range(num_workers):
            p = mp.Process(
                target=self._spawn_pool_worker,
                args=(model, new_adapter, meta.get('hold_seconds', 600), meta.get('variant')),
                daemon=True,
            )
            p.start()
            procs.append(p)
            time.sleep(0.2)

        # Wait for a short warm period
        time.sleep(min(wait_seconds, 30))

        # stop old pool
        old_procs = meta.get('procs', [])
        for p in old_procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in old_procs:
            try:
                p.join(timeout=1.0)
            except Exception:
                pass

        # Replace metadata
        self._WORKER_POOLS[pool_id] = {
            'model': model,
            'adapter': new_adapter,
            'num_workers': num_workers,
            'procs': procs,
            'started_at': time.time(),
            'hold_seconds': meta.get('hold_seconds', 600),
            'variant': meta.get('variant'),
        }

        # audit swap
        self._audit_worker_pool_event('swap_adapter', pool_id, model, new_adapter, num_workers, requestor=requestor, variant=meta.get('variant'))
        return {'pool_id': pool_id, 'status': 'swapped', 'new_adapter': new_adapter}

    def _audit_worker_pool_event(self, action: str, pool_id: str, model_id: str | None, adapter: str | None, num_workers: int, requestor: dict | None = None, variant: str | None = None):
        try:
            audit_dir = Path('logs/audit')
            audit_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                'timestamp': time.time(),
                'action': action,
                'pool_id': pool_id,
                'model_id': model_id,
                'adapter': adapter,
                'num_workers': num_workers,
            }
            if variant:
                entry['variant'] = variant
            if requestor:
                entry['requestor'] = requestor
            # optionally include requestor identity when available (controller should add 'requestor' key)
            # Write as JSON line
            with open(audit_dir / 'gpu_orchestrator_worker_pools.jsonl', 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            # Do not fail the operation if auditing fails
            self.logger.warning('Failed to write worker pool audit entry')

    def _audit_policy_event(self, action: str, detail: dict, requestor: dict | None = None):
        try:
            audit_dir = Path('logs/audit')
            audit_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                'timestamp': time.time(),
                'action': action,
                'detail': detail,
            }
            if requestor:
                entry['requestor'] = requestor

            with open(audit_dir / 'gpu_orchestrator_pool_policy.jsonl', 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            self.logger.warning('Failed to write policy audit entry')

    def _rehydrate_worker_pools_from_db(self) -> None:
        """Load persisted worker pools from DB into memory without spawning processes.

        This is a best-effort, read-only hydration used during startup so the orchestrator
        can represent existing pools and reconcile them later.
        """
        try:
            cursor = self.db_service.mb_conn.cursor(dictionary=True)
            cursor.execute("SELECT pool_id, agent_name, model_id, adapter, desired_workers, spawned_workers, started_at, status, hold_seconds, metadata FROM worker_pools WHERE status IN ('starting','running','draining')")
            rows = cursor.fetchall()
            cursor.close()

            for r in rows:
                pid = r.get('pool_id')
                # We don't (re)spawn processes here — just restore metadata for reconciliation
                self._WORKER_POOLS[pid] = {
                    'model': r.get('model_id'),
                    'adapter': r.get('adapter'),
                    'num_workers': int(r.get('desired_workers') or 0),
                    'procs': [],
                    'started_at': (r.get('started_at').timestamp() if getattr(r.get('started_at'), 'timestamp', None) else None),
                    'hold_seconds': int(r.get('hold_seconds') or 600),
                    'variant': (r.get('metadata') and (json.loads(r.get('metadata')).get('variant') if isinstance(r.get('metadata'), str) else r.get('metadata', {}).get('variant'))) or None,
                }

            # Update metrics
            self.worker_pools_gauge.labels(agent=self.metrics.agent_name, agent_display_name=self.metrics.display_name).set(len(self._WORKER_POOLS))
        except Exception as e:
            # Do not fail startup, just log
            self.logger.debug(f'Error rehydrating worker pools from DB: {e}')

    def get_mps_allocation_config(self) -> dict[str, Any]:
        """Get MPS allocation configuration."""
        try:
            import json
            project_root = Path(self._project_root())
            config_path = project_root / "config" / "gpu" / "mps_allocation_config.json"

            if not config_path.exists():
                return {"error": "MPS allocation configuration not found", "path": str(config_path)}

            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load MPS allocation config: {e}")
            return {"error": str(e)}

    def get_metrics_text(self) -> str:
        """Get Prometheus metrics as text."""
        from prometheus_client import generate_latest
        return generate_latest(self.metrics.registry).decode('utf-8')

    # Job queue helpers
    def submit_job(self, job_id: str, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a job row and push into Redis stream (fallback to DB-only if Redis unavailable)."""
        try:
            # Persist job to DB if available
            if self.db_service:
                cursor = self.db_service.mb_conn.cursor()
                cursor.execute(
                    "INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts, created_at) VALUES (%s,%s,%s,%s,%s,NOW())",
                    (job_id, job_type, json.dumps(payload), 'pending', 0)
                )
                self.db_service.mb_conn.commit()
                cursor.close()

            # Try to push to Redis stream if available
            if self.redis_client:
                try:
                    # stream name is type-based, fallback to generic inference_jobs
                    stream = os.environ.get('ORCH_STREAM_PREFIX', 'stream:orchestrator:') + (job_type or 'inference_jobs')
                    # store payload as JSON string under 'payload'
                    self.redis_client.xadd(stream, {'job_id': job_id, 'type': job_type, 'payload': json.dumps(payload)})
                except Exception:
                    # Non-fatal; keep job persisted in DB
                    self.logger.debug('Failed to write job to Redis stream (non-fatal)')

            return {'job_id': job_id, 'status': 'submitted'}
        except Exception as e:
            self.logger.error(f'Failed to submit job: {e}')
            raise

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve job record from DB if available, else return from in-memory cache if present."""
        try:
            if self.db_service:
                cursor = self.db_service.mb_conn.cursor(dictionary=True)
                cursor.execute("SELECT job_id, type, payload, status, attempts, created_at, updated_at, last_error FROM orchestrator_jobs WHERE job_id=%s", (job_id,))
                row = cursor.fetchone()
                cursor.close()
                if row:
                    # parse payload JSON
                    try:
                        row['payload'] = json.loads(row['payload']) if row.get('payload') else {}
                    except Exception:
                        pass
                    return row
            # fallback not found
            return None
        except Exception as e:
            self.logger.debug(f'Failed to read job from DB: {e}')
            return None

    def _reclaimer_pass(self):
        """Single pass over orchestrator streams to reclaim or move stale pending messages.

        For each stream we examine pending messages older than _claim_idle_ms, increment attempts
        in the job table, and either requeue them or send to DLQ if attempts exceed threshold.
        """
        if not self.redis_client:
            return

        streams = [
            os.environ.get('ORCH_STREAM_PREFIX', 'stream:orchestrator:') + 'inference_jobs',
            os.environ.get('ORCH_STREAM_PREFIX', 'stream:orchestrator:') + 'preloads'
        ]

        for s in streams:
            try:
                # xpending_range returns list of pending entries
                # we use a small window per pass for risk mitigation
                pending = []
                try:
                    # xpending_range exists on newer redis clients; fall back to xpending if needed
                    pending = self.redis_client.xpending_range(s, 'cg:inference', '-', '+', count=100)
                except Exception:
                    # Not supported: try using XPENDING summary -> get count and range via XINFO/PENDING not ideal
                    try:
                        resp = self.redis_client.xpending(s, 'cg:inference')
                        # can't parse easily; skip in this fallback
                        pending = []
                    except Exception:
                        pending = []

                for entry in pending:
                    try:
                        # entry is (message_id, consumer, idle, delivered_count)
                        msg_id = entry[0]
                        idle = int(entry[2]) if len(entry) > 2 else 0
                        if idle < self._claim_idle_ms:
                            continue

                        # read full message so we can inspect job_id and payload
                        entries = self.redis_client.xrange(s, min=msg_id, max=msg_id)
                        if not entries:
                            continue
                        _, fields = entries[0]
                        job_id = None
                        payload = None
                        if b'job_id' in fields or 'job_id' in fields:
                            job_id = fields.get(b'job_id') or fields.get('job_id')
                            if isinstance(job_id, bytes):
                                job_id = job_id.decode('utf-8')
                        pld = fields.get(b'payload') or fields.get('payload')
                        if pld:
                            if isinstance(pld, bytes):
                                try:
                                    payload = json.loads(pld.decode('utf-8'))
                                except Exception:
                                    payload = pld.decode('utf-8')
                            else:
                                try:
                                    payload = json.loads(pld)
                                except Exception:
                                    payload = pld

                        # fetch DB attempts (best-effort)
                        attempts = 0
                        if job_id and self.db_service:
                            try:
                                cursor = self.db_service.mb_conn.cursor()
                                cursor.execute('SELECT attempts FROM orchestrator_jobs WHERE job_id=%s', (job_id,))
                                r = cursor.fetchone()
                                cursor.close()
                                if r:
                                    attempts = int(r[0])
                            except Exception:
                                attempts = attempts

                        attempts += 1

                        if job_id and self.db_service:
                            try:
                                cursor = self.db_service.mb_conn.cursor()
                                cursor.execute('UPDATE orchestrator_jobs SET attempts=%s, updated_at=NOW() WHERE job_id=%s', (attempts, job_id))
                                self.db_service.mb_conn.commit()
                                cursor.close()
                            except Exception:
                                pass

                        if attempts >= self._job_retry_max:
                            # move to DLQ
                            dlq = s + ':dlq'
                            try:
                                self.redis_client.xadd(dlq, {'job_id': job_id or '', 'payload': json.dumps(payload) if payload is not None else ''})
                            except Exception:
                                pass
                            # mark job dead-lettered in DB
                            if job_id and self.db_service:
                                try:
                                    cursor = self.db_service.mb_conn.cursor()
                                    cursor.execute('UPDATE orchestrator_jobs SET status=%s, last_error=%s, updated_at=NOW() WHERE job_id=%s', ('dead_letter', 'max_attempts_exceeded', job_id))
                                    self.db_service.mb_conn.commit()
                                    cursor.close()
                                except Exception:
                                    pass
                            # ack original message
                            try:
                                self.redis_client.xack(s, 'cg:inference', msg_id)
                            except Exception:
                                pass
                        else:
                            # requeue message as a new message for processing
                            try:
                                self.redis_client.xadd(s, {'job_id': job_id or '', 'type': fields.get(b'type') or fields.get('type') or '', 'payload': json.dumps(payload) if payload is not None else ''})
                                self.redis_client.xack(s, 'cg:inference', msg_id)
                            except Exception:
                                pass

                    except Exception:
                        # protect loop from bad entries
                        pass
            except Exception:
                # ignore stream errors, continue next stream
                pass

    def _reclaimer_loop(self):
        while True:
            try:
                self._reclaimer_pass()
            except Exception:
                pass
            time.sleep(self._reclaim_interval_s)


# Global engine instance
engine = GPUOrchestratorEngine()
