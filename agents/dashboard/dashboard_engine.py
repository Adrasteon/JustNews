"""
Dashboard Engine - Core logic for JustNewsAgent Dashboard

This module contains the core business logic for the dashboard agent,
including GPU monitoring, storage operations, and system health checks.
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .storage import get_storage
from agents.common.gpu_manager_production import get_gpu_manager

logger = logging.getLogger(__name__)

# Load configuration
def _load_config() -> dict:
    """Load dashboard configuration."""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        try:
            import json
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")
    return {}

_config = _load_config()
MCP_BUS_URL = _config.get("mcp_bus_url", "http://localhost:8000")


class ToolCall(BaseModel):
    """Standard MCP tool call format"""
    args: list
    kwargs: dict[str, Any]


class EnhancedGPUMonitor:
    """Enhanced GPU monitoring with comprehensive tracking and fallbacks."""

    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        self.gpu_history: List[dict] = []
        self.gpu_manager = None

        # Try to initialize GPU manager
        try:
            self.gpu_manager = get_gpu_manager()
            logger.info("GPU manager initialized successfully")
        except Exception as e:
            logger.warning(f"GPU manager not available: {e}")
            self.gpu_manager = None

    def get_gpu_info(self) -> dict:
        """Get current GPU information using GPU manager or nvidia-smi fallback."""
        try:
            if self.gpu_manager:
                # Try GPU manager first
                system_status = self.gpu_manager.get_system_status()
                gpu_info = system_status.get('gpu_info', {})

                if gpu_info:
                    gpus = []
                    for gpu in gpu_info.get('gpus', []):
                        gpu_data = {
                            'index': gpu.get('index', 0),
                            'name': gpu.get('name', 'Unknown'),
                            'memory_used_mb': gpu.get('memory_used_mb', 0),
                            'memory_total_mb': gpu.get('memory_total_mb', 0),
                            'memory_free_mb': gpu.get('memory_free_mb', 0),
                            'gpu_utilization_percent': gpu.get('utilization_percent', 0),
                            'memory_utilization_percent': gpu.get('memory_utilization_percent', 0),
                            'temperature_celsius': gpu.get('temperature_celsius', 0),
                            'fan_speed_percent': gpu.get('fan_speed_percent', 0),
                            'power_draw_watts': gpu.get('power_draw_watts', 0.0),
                            'power_limit_watts': gpu.get('power_limit_watts', 0.0),
                            'is_healthy': gpu.get('is_healthy', True),
                            'timestamp': time.time()
                        }
                        gpus.append(gpu_data)

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
                        storage = get_storage()
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
                    return self._get_nvidia_smi_fallback()
            else:
                return self._get_nvidia_smi_fallback()

        except Exception as e:
            logger.error(f"Error getting GPU info: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': time.time()
            }

    def _get_nvidia_smi_fallback(self) -> dict:
        """Fallback GPU monitoring using nvidia-smi."""
        try:
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
                    storage = get_storage()
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


class DashboardEngine:
    """Core dashboard engine handling monitoring, storage, and system operations."""

    def __init__(self):
        self.gpu_monitor = EnhancedGPUMonitor()
        self.storage = get_storage()
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load dashboard configuration."""
        config_path = Path(__file__).parent / "config.json"
        if config_path.exists():
            try:
                import json
                with open(config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return {}

    def save_config(self, config: dict):
        """Save dashboard configuration."""
        config_path = Path(__file__).parent / "config.json"
        try:
            import json
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get_agent_status(self) -> dict:
        """Fetch the status of all agents."""
        try:
            response = requests.get(f"{MCP_BUS_URL}/agents")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"An error occurred while fetching agent status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def send_command(self, call: ToolCall) -> dict:
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

    def get_gpu_config(self) -> dict:
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
                    "config": self.config.get("gpu_config", {}),
                    "timestamp": time.time()
                }
        except Exception as e:
            logger.error(f"Error getting GPU config: {e}")
            return {
                "status": "error",
                "message": str(e),
                "timestamp": time.time()
            }

    def update_gpu_config(self, new_config: dict) -> dict:
        """Update GPU configuration."""
        try:
            # Try to update via GPU manager
            response = requests.post("http://localhost:8000/gpu/config", json=new_config, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                # Fallback to local update
                if "gpu_config" not in self.config:
                    self.config["gpu_config"] = {}
                self.config["gpu_config"].update(new_config)
                self.save_config(self.config)
                return {
                    "status": "success",
                    "source": "dashboard_fallback",
                    "message": "Configuration updated locally",
                    "config": self.config["gpu_config"],
                    "timestamp": time.time()
                }
        except Exception as e:
            logger.error(f"Error updating GPU config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_gpu_manager_status(self) -> dict:
        """Get comprehensive GPU manager system status."""
        try:
            if self.gpu_monitor.gpu_manager:
                system_status = self.gpu_monitor.gpu_manager.get_system_status()
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

    def get_gpu_allocations(self) -> dict:
        """Get all current GPU allocations."""
        try:
            if self.gpu_monitor.gpu_manager:
                # Get allocation data from GPU manager
                allocations = []
                agent_names = ['scout', 'fact_checker', 'analyst', 'synthesizer', 'critic', 'memory', 'newsreader']
                for agent_name in agent_names:
                    allocation_status = self.gpu_monitor.gpu_manager.get_allocation_status(agent_name)
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

    def get_gpu_metrics(self) -> dict:
        """Get GPU performance metrics from the manager."""
        try:
            if self.gpu_monitor.gpu_manager:
                system_status = self.gpu_monitor.gpu_manager.get_system_status()
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

    def get_gpu_history_from_db(self, hours: int = 24, gpu_index: int | None = None, metric: str = "utilization") -> dict:
        """Get GPU metrics history from database."""
        try:
            if metric == "utilization":
                history = self.storage.get_gpu_metrics_history(hours, gpu_index, metric_type="utilization")
            elif metric == "memory":
                history = self.storage.get_gpu_metrics_history(hours, gpu_index, metric_type="memory_used_mb")
            elif metric == "temperature":
                history = self.storage.get_gpu_metrics_history(hours, gpu_index, metric_type="temperature_celsius")
            elif metric == "performance":
                # For performance, we'll use processing time or similar metrics
                history = self.storage.get_performance_trends(hours)
            else:
                history = self.storage.get_gpu_metrics_history(hours, gpu_index)

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

    def get_allocation_history(self, hours: int = 24, agent_name: str | None = None) -> dict:
        """Get agent allocation history from database."""
        try:
            history = self.storage.get_agent_allocation_history(hours, agent_name)
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

    def get_performance_trends(self, hours: int = 24) -> dict:
        """Get performance trends data."""
        try:
            trends = self.storage.get_performance_trends(hours)
            return {
                'status': 'success',
                'hours': hours,
                'trends': trends,
                'timestamp': time.time()
            }
        except Exception as e:
            logger.error(f"Error getting performance trends: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_recent_alerts(self, limit: int = 50) -> dict:
        """Get recent alerts from database."""
        try:
            alerts = self.storage.get_recent_alerts(limit)
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

    def get_storage_stats(self) -> dict:
        """Get database storage statistics."""
        try:
            stats = self.storage.get_storage_stats()
            return {
                'status': 'success',
                'storage_stats': stats,
                'timestamp': time.time()
            }
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_comprehensive_gpu_dashboard_data(self) -> dict:
        """Get comprehensive GPU dashboard data including manager integration."""
        try:
            gpu_info = self.gpu_monitor.get_gpu_info()
            orchestrator_policy = self._fetch_orchestrator_policy()
            agent_usage = self.gpu_monitor.get_agent_gpu_usage()
            gpu_config = self.get_gpu_config()

            # Get additional data from GPU manager if available
            manager_status = None
            allocations = []
            metrics = {}

            if self.gpu_monitor.gpu_manager:
                manager_status = self.gpu_monitor.gpu_manager.get_system_status()

                # Get allocations
                agent_names = ['scout', 'fact_checker', 'analyst', 'synthesizer', 'critic', 'memory', 'newsreader']
                for agent_name in agent_names:
                    allocation_status = self.gpu_monitor.gpu_manager.get_allocation_status(agent_name)
                    if allocation_status:
                        allocations.append(allocation_status)

                metrics = manager_status.get('metrics', {})

            # Calculate enhanced summary
            summary = {
                "total_gpus": gpu_info.get("gpu_count", 0),
                "total_memory_used_mb": agent_usage.get("total_memory_used_mb", 0),
                "active_agents": sum(1 for agent in agent_usage.get("agents", {}).values() if agent.get("active", False)),
                "gpu_utilization_avg": sum(gpu.get("gpu_utilization_percent", 0) for gpu in gpu_info.get("gpus", [])) / max(1, len(gpu_info.get("gpus", []))),
                "gpu_manager_available": self.gpu_monitor.gpu_manager is not None,
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
                    "available": self.gpu_monitor.gpu_manager is not None,
                    "status": manager_status,
                    "allocations": allocations,
                    "metrics": metrics
                },
                "orchestrator_policy": orchestrator_policy,
                "summary": summary
            }
        except Exception as e:
            logger.error(f"Error in get_comprehensive_gpu_dashboard_data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _fetch_orchestrator_policy(self) -> dict:
        """Fetch policy from orchestrator (fast timeout)."""
        try:
            response = requests.get("http://localhost:8000/policy", timeout=(1.5, 3.0))
            if response.status_code == 200:
                return response.json()
            return {"safe_mode_read_only": True, "error": f"unexpected_status:{response.status_code}"}
        except Exception as e:
            return {"safe_mode_read_only": True, "error": str(e)}

    def ingest_gpu_jsonl(self, path: str, max_lines: int | None = 10000) -> dict:
        """Ingest GPU watcher JSONL into dashboard storage."""
        try:
            in_path = path
            if not os.path.isabs(in_path):
                # Resolve relative to project root
                in_path = str((Path(__file__).resolve().parents[2] / path).resolve())

            if not os.path.exists(in_path):
                raise HTTPException(status_code=404, detail=f"File not found: {in_path}")

            ingested_points = 0
            max_lines = max_lines or 10000

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
                        self._ingest_single_gpu_record(record)
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
                                self._ingest_single_gpu_record(rec)
                                ingested_points += 1
                            except Exception:
                                continue

                    if isinstance(data, dict):
                        # Support known containers: records, samples
                        if "records" in data and isinstance(data["records"], list):
                            for rec in data["records"][:max_lines]:
                                self._ingest_single_gpu_record(rec)
                                ingested_points += 1
                        elif "samples" in data and isinstance(data["samples"], list):
                            for rec in data["samples"][:max_lines]:
                                self._ingest_single_gpu_record(rec)
                                ingested_points += 1
                    elif isinstance(data, list):
                        for rec in data[:max_lines]:
                            self._ingest_single_gpu_record(rec)
                            ingested_points += 1

            return {"status": "success", "ingested_records": ingested_points, "path": in_path, "timestamp": time.time()}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error ingesting GPU JSONL: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _ingest_single_gpu_record(self, record: dict) -> None:
        """Normalize and store a single GPU watcher record into storage."""
        try:
            ts = record.get("time") or record.get("timestamp") or time.time()
            if isinstance(ts, str):
                epoch = self._parse_iso8601_to_epoch(ts)
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
                self.storage.store_gpu_metrics({"gpus": gpus})
        except Exception as e:
            logger.warning(f"Failed to ingest single GPU record: {e}")

    def _parse_iso8601_to_epoch(self, ts_str: str) -> float:
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


# Global dashboard engine instance
dashboard_engine = DashboardEngine()