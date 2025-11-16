"""
Tools and utilities for the Balancer Agent.
"""
from typing import Any

from .balancer_engine import BalancerEngine

# Global engine instance
_balancer_engine = BalancerEngine()


def distribute_load(workload_items: list[dict[str, Any]], agent_count: int = 8) -> dict[str, Any]:
    """Distribute workload items across available agents for load balancing."""
    return _balancer_engine.distribute_load(workload_items, agent_count)


def get_agent_status() -> dict[str, Any]:
    """Get status of all agents for load balancing decisions."""
    return _balancer_engine.get_agent_status()


def balance_workload(current_loads: dict[str, float] = None) -> dict[str, Any]:
    """Balance workload based on current agent loads."""
    return _balancer_engine.balance_workload(current_loads)


def monitor_performance(monitoring_window_seconds: int = 300) -> dict[str, Any]:
    """Monitor agent performance metrics for load balancing."""
    return _balancer_engine.monitor_performance(monitoring_window_seconds)
