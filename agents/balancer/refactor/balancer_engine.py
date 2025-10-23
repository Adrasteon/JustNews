"""
Balancer Engine for JustNewsAgent.

Core load balancing and workload distribution logic.
"""
from typing import Dict, List, Any
import time
import random

from common.observability import get_logger

logger = get_logger(__name__)


class BalancerEngine:
    """
    Engine for load balancing and workload distribution across agents.
    """

    def __init__(self):
        self.agent_status_cache = {}
        self.last_status_update = 0
        self.cache_ttl = 30  # 30 seconds cache

    def distribute_load(self, workload_items: List[Dict[str, Any]], agent_count: int = 8) -> Dict[str, Any]:
        """Distribute workload items across available agents for load balancing."""
        if not workload_items:
            return {"distribution": {}, "total_items": 0, "agents_used": 0}

        # Simple round-robin distribution
        distribution = {}
        for i in range(agent_count):
            distribution[f"agent_{i+1}"] = []

        for idx, item in enumerate(workload_items):
            agent_idx = idx % agent_count
            agent_name = f"agent_{agent_idx + 1}"
            distribution[agent_name].append(item)

        return {
            "distribution": distribution,
            "total_items": len(workload_items),
            "agents_used": agent_count,
            "avg_load_per_agent": len(workload_items) / agent_count,
            "distribution_method": "round_robin"
        }

    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents for load balancing decisions."""
        # Check cache first
        current_time = time.time()
        if current_time - self.last_status_update < self.cache_ttl and self.agent_status_cache:
            return self.agent_status_cache

        # Simulate agent status (in real implementation, this would query actual agents)
        agents = ["scout", "analyst", "fact_checker", "synthesizer", "critic",
                  "memory", "reasoning", "chief_editor", "training_system"]

        agent_status = {}
        for agent in agents:
            # Simulate realistic status data
            agent_status[agent] = {
                "status": "active" if random.random() > 0.1 else "busy",  # 90% active, 10% busy
                "current_load": random.randint(0, 100),
                "queue_size": random.randint(0, 50),
                "response_time_ms": random.randint(50, 500),
                "last_heartbeat": current_time - random.randint(0, 30),
                "memory_usage_mb": random.randint(100, 2000),
                "cpu_usage_pct": random.randint(5, 95)
            }

        result = {
            "agents": agent_status,
            "total_agents": len(agents),
            "active_agents": sum(1 for status in agent_status.values() if status["status"] == "active"),
            "timestamp": current_time
        }

        # Update cache
        self.agent_status_cache = result
        self.last_status_update = current_time

        return result

    def balance_workload(self, current_loads: Dict[str, float] = None) -> Dict[str, Any]:
        """Balance workload based on current agent loads."""
        if current_loads is None:
            # Get current loads from agent status
            status = self.get_agent_status()
            current_loads = {agent: info["current_load"] for agent, info in status["agents"].items()}

        # Calculate load statistics
        loads = list(current_loads.values())
        avg_load = sum(loads) / len(loads)
        max_load = max(loads)
        min_load = min(loads)

        # Identify overloaded and underloaded agents
        overloaded = [agent for agent, load in current_loads.items() if load > 80]
        underloaded = [agent for agent, load in current_loads.items() if load < 30]

        # Generate balancing recommendations
        recommendations = []

        if overloaded and underloaded:
            for over_agent in overloaded:
                for under_agent in underloaded:
                    recommendations.append({
                        "action": "redistribute",
                        "from_agent": over_agent,
                        "to_agent": under_agent,
                        "estimated_improvement": min(20, current_loads[over_agent] - avg_load)
                    })

        return {
            "current_loads": current_loads,
            "statistics": {
                "average_load": avg_load,
                "max_load": max_load,
                "min_load": min_load,
                "load_variance": sum((load - avg_load) ** 2 for load in loads) / len(loads)
            },
            "overloaded_agents": overloaded,
            "underloaded_agents": underloaded,
            "recommendations": recommendations,
            "balancing_needed": len(overloaded) > 0 or len(underloaded) > 0
        }

    def monitor_performance(self, monitoring_window_seconds: int = 300) -> Dict[str, Any]:
        """Monitor agent performance metrics for load balancing."""
        # Get current agent status
        status = self.get_agent_status()

        # Calculate performance metrics
        performance_metrics = {}

        for agent_name, agent_info in status["agents"].items():
            # Calculate throughput (simulated)
            base_throughput = 100  # items per minute
            load_factor = agent_info["current_load"] / 100.0
            current_throughput = base_throughput * (1 - load_factor * 0.5)  # Load reduces throughput

            # Calculate efficiency
            efficiency = current_throughput / base_throughput

            performance_metrics[agent_name] = {
                "throughput_items_per_minute": current_throughput,
                "efficiency": efficiency,
                "response_time_ms": agent_info["response_time_ms"],
                "queue_size": agent_info["queue_size"],
                "memory_usage_mb": agent_info["memory_usage_mb"],
                "cpu_usage_pct": agent_info["cpu_usage_pct"],
                "health_score": 100 - agent_info["current_load"]  # Simple health calculation
            }

        # Overall system performance
        avg_throughput = sum(m["throughput_items_per_minute"] for m in performance_metrics.values()) / len(performance_metrics)
        avg_efficiency = sum(m["efficiency"] for m in performance_metrics.values()) / len(performance_metrics)
        avg_response_time = sum(m["response_time_ms"] for m in performance_metrics.values()) / len(performance_metrics)

        return {
            "performance_metrics": performance_metrics,
            "system_summary": {
                "average_throughput": avg_throughput,
                "average_efficiency": avg_efficiency,
                "average_response_time_ms": avg_response_time,
                "total_queue_size": sum(m["queue_size"] for m in performance_metrics.values()),
                "monitoring_window_seconds": monitoring_window_seconds
            },
            "bottlenecks": [
                agent for agent, metrics in performance_metrics.items()
                if metrics["efficiency"] < 0.7 or metrics["queue_size"] > 25
            ],
            "timestamp": time.time()
        }