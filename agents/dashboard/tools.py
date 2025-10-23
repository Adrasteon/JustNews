"""
from common.observability import get_logger
Tools for the Dashboard Agent.
"""


import time

logger = get_logger(__name__)

def log_event(event: str, details: dict):
    """Logs an event for the dashboard agent."""
    logger.info(f"Event: {event}, Details: {details}")

def format_status_response(status_data: dict) -> dict:
    """Formats the status response for the dashboard UI."""
    return {
        "agent_count": len(status_data),
        "agents": status_data
    }

def process_command_response(response: dict) -> dict:
    """Processes the response from a command sent to another agent."""
    return {
        "status": response.get("status", "unknown"),
        "details": response
    }

def get_gpu_metrics() -> dict:
    """Get current GPU metrics from nvidia-smi."""
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            gpu_data = []
            for line in lines:
                if line.strip():
                    parts = [part.strip() for part in line.split(',')]
                    if len(parts) >= 6:
                        gpu_data.append({
                            'index': int(parts[0]),
                            'name': parts[1],
                            'memory_used_mb': int(parts[2]),
                            'memory_total_mb': int(parts[3]),
                            'utilization_percent': int(parts[4]),
                            'temperature_celsius': int(parts[5]),
                            'timestamp': time.time()
                        })

            return {
                'status': 'success',
                'gpu_count': len(gpu_data),
                'gpus': gpu_data,
                'timestamp': time.time()
            }
        else:
            return {
                'status': 'error',
                'message': f'nvidia-smi command failed: {result.stderr}',
                'timestamp': time.time()
            }
    except Exception as e:
        logger.error(f"Error getting GPU metrics: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'timestamp': time.time()
        }

def format_gpu_dashboard_data(gpu_info: dict, agent_usage: dict) -> dict:
    """Format GPU data for dashboard display."""
    try:
        gpus = gpu_info.get('gpus', [])
        agents = agent_usage.get('agents', {})

        # Calculate summary statistics
        total_memory = sum(gpu.get('memory_total_mb', 0) for gpu in gpus)
        used_memory = sum(gpu.get('memory_used_mb', 0) for gpu in gpus)
        avg_utilization = sum(gpu.get('utilization_percent', 0) for gpu in gpus) / max(1, len(gpus))
        max_temp = max((gpu.get('temperature_celsius', 0) for gpu in gpus), default=0)

        # Agent activity summary
        active_agents = sum(1 for agent in agents.values() if agent.get('active', False))
        total_agent_memory = sum(agent.get('memory_used_mb', 0) for agent in agents.values())

        return {
            'summary': {
                'gpu_count': len(gpus),
                'total_memory_mb': total_memory,
                'used_memory_mb': used_memory,
                'memory_utilization_percent': (used_memory / max(1, total_memory)) * 100,
                'avg_gpu_utilization_percent': avg_utilization,
                'max_temperature_celsius': max_temp,
                'active_agents': active_agents,
                'total_agent_memory_mb': total_agent_memory
            },
            'gpus': gpus,
            'agents': agents,
            'alerts': generate_gpu_alerts(gpus, agents),
            'timestamp': time.time()
        }
    except Exception as e:
        logger.error(f"Error formatting GPU dashboard data: {e}")
        return {
            'summary': {},
            'gpus': [],
            'agents': {},
            'alerts': [],
            'timestamp': time.time()
        }

def generate_gpu_alerts(gpus: list[dict], agents: dict) -> list[dict]:
    """Generate alerts based on GPU metrics."""
    alerts = []

    for gpu in gpus:
        # High temperature alert
        if gpu.get('temperature_celsius', 0) > 80:
            alerts.append({
                'type': 'warning',
                'category': 'temperature',
                'message': f"GPU {gpu['index']} temperature is high: {gpu['temperature_celsius']}°C",
                'gpu_index': gpu['index'],
                'value': gpu['temperature_celsius'],
                'threshold': 80
            })

        # High memory usage alert
        memory_usage_percent = (gpu.get('memory_used_mb', 0) / max(1, gpu.get('memory_total_mb', 1))) * 100
        if memory_usage_percent > 90:
            alerts.append({
                'type': 'warning',
                'category': 'memory',
                'message': f"GPU {gpu['index']} memory usage is high: {memory_usage_percent:.1f}%",
                'gpu_index': gpu['index'],
                'value': memory_usage_percent,
                'threshold': 90
            })

        # High utilization alert
        if gpu.get('utilization_percent', 0) > 95:
            alerts.append({
                'type': 'info',
                'category': 'utilization',
                'message': f"GPU {gpu['index']} utilization is very high: {gpu['utilization_percent']}%",
                'gpu_index': gpu['index'],
                'value': gpu['utilization_percent'],
                'threshold': 95
            })

    # Check for inactive agents with high memory usage
    for agent_name, agent_data in agents.items():
        if not agent_data.get('active', False) and agent_data.get('memory_used_mb', 0) > 100:
            alerts.append({
                'type': 'info',
                'category': 'agent',
                'message': f"Agent {agent_name} is inactive but using {agent_data['memory_used_mb']}MB GPU memory",
                'agent': agent_name,
                'memory_mb': agent_data['memory_used_mb']
            })

    return alerts

def get_performance_analytics(hours: int = 24) -> dict:
    """Get performance analytics for the specified time period."""
    try:
        # This would typically query a database or time-series storage
        # For now, return mock analytics data
        return {
            'status': 'success',
            'period_hours': hours,
            'analytics': {
                'avg_gpu_utilization': 45.2,
                'peak_gpu_utilization': 89.5,
                'avg_memory_usage_mb': 3200,
                'peak_memory_usage_mb': 7200,
                'total_agent_runtime_hours': 18.5,
                'performance_trends': {
                    'utilization_trend': 'stable',
                    'memory_trend': 'increasing',
                    'efficiency_score': 85.3
                },
                'recommendations': [
                    'Consider increasing batch sizes for better GPU utilization',
                    'Memory usage is trending up - monitor for potential leaks',
                    'Current configuration is optimal for workload'
                ]
            },
            'timestamp': time.time()
        }
    except Exception as e:
        logger.error(f"Error getting performance analytics: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'timestamp': time.time()
        }
