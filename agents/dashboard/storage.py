"""
Historical data storage for GPU monitoring dashboard.
Provides SQLite-based storage for metrics, allocations, and performance trends.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from common.observability import get_logger

logger = get_logger(__name__)

class DashboardStorage:
    """SQLite-based storage for dashboard historical data."""

    def __init__(self, db_path: str = "dashboard_history.db"):
        self.db_path = os.path.join(os.path.dirname(__file__), db_path)
        self._init_db()

    def _init_db(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # GPU metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gpu_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    gpu_index INTEGER NOT NULL,
                    name TEXT,
                    memory_used_mb REAL,
                    memory_total_mb REAL,
                    memory_free_mb REAL,
                    gpu_utilization_percent REAL,
                    memory_utilization_percent REAL,
                    temperature_celsius REAL,
                    fan_speed_percent REAL,
                    power_draw_watts REAL,
                    power_limit_watts REAL,
                    is_healthy BOOLEAN,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')

            # Agent allocations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS agent_allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    agent_name TEXT NOT NULL,
                    gpu_device INTEGER,
                    allocated_memory_gb REAL,
                    batch_size INTEGER,
                    model_type TEXT,
                    status TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')

            # Performance metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL,
                    metadata TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')

            # Alerts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    alert_type TEXT NOT NULL,
                    category TEXT,
                    message TEXT NOT NULL,
                    severity TEXT DEFAULT 'info',
                    gpu_index INTEGER,
                    value REAL,
                    threshold REAL,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_at REAL,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')

            # Create indexes for better query performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_gpu_metrics_timestamp ON gpu_metrics(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_gpu_metrics_gpu_index ON gpu_metrics(gpu_index)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_allocations_timestamp ON agent_allocations(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_allocations_agent ON agent_allocations(agent_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_performance_metrics_timestamp ON performance_metrics(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_performance_metrics_name ON performance_metrics(metric_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type)')

            conn.commit()
            logger.info("Dashboard storage database initialized")

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def store_gpu_metrics(self, metrics_data: dict):
        """Store GPU metrics data."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                if 'gpus' in metrics_data:
                    for gpu in metrics_data['gpus']:
                        cursor.execute('''
                            INSERT INTO gpu_metrics (
                                timestamp, gpu_index, name, memory_used_mb, memory_total_mb,
                                memory_free_mb, gpu_utilization_percent, memory_utilization_percent,
                                temperature_celsius, fan_speed_percent, power_draw_watts,
                                power_limit_watts, is_healthy
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            gpu.get('timestamp', datetime.now().timestamp()),
                            gpu.get('index', 0),
                            gpu.get('name', ''),
                            gpu.get('memory_used_mb'),
                            gpu.get('memory_total_mb'),
                            gpu.get('memory_free_mb'),
                            gpu.get('gpu_utilization_percent'),
                            gpu.get('memory_utilization_percent'),
                            gpu.get('temperature_celsius'),
                            gpu.get('fan_speed_percent'),
                            gpu.get('power_draw_watts'),
                            gpu.get('power_limit_watts'),
                            gpu.get('is_healthy', True)
                        ))

                conn.commit()
                logger.debug(f"Stored GPU metrics for {len(metrics_data.get('gpus', []))} GPUs")

        except Exception as e:
            logger.error(f"Error storing GPU metrics: {e}")

    def store_agent_allocations(self, allocations_data: list[dict]):
        """Store agent allocation data."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                for allocation in allocations_data:
                    cursor.execute('''
                        INSERT INTO agent_allocations (
                            timestamp, agent_name, gpu_device, allocated_memory_gb,
                            batch_size, model_type, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        allocation.get('timestamp', datetime.now().timestamp()),
                        allocation.get('agent_name', ''),
                        allocation.get('gpu_device'),
                        allocation.get('allocated_memory_gb'),
                        allocation.get('batch_size'),
                        allocation.get('model_type', 'general'),
                        allocation.get('status', 'active')
                    ))

                conn.commit()
                logger.debug(f"Stored {len(allocations_data)} agent allocations")

        except Exception as e:
            logger.error(f"Error storing agent allocations: {e}")

    def store_performance_metrics(self, metrics: dict):
        """Store performance metrics."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                timestamp = metrics.get('timestamp', datetime.now().timestamp())

                # Store each metric
                for key, value in metrics.items():
                    if key != 'timestamp' and isinstance(value, (int, float)):
                        cursor.execute('''
                            INSERT INTO performance_metrics (
                                timestamp, metric_name, metric_value
                            ) VALUES (?, ?, ?)
                        ''', (timestamp, key, value))

                conn.commit()
                logger.debug(f"Stored performance metrics: {list(metrics.keys())}")

        except Exception as e:
            logger.error(f"Error storing performance metrics: {e}")

    def store_alert(self, alert_data: dict):
        """Store an alert."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO alerts (
                        timestamp, alert_type, category, message, severity,
                        gpu_index, value, threshold
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    alert_data.get('timestamp', datetime.now().timestamp()),
                    alert_data.get('type', 'info'),
                    alert_data.get('category', ''),
                    alert_data.get('message', ''),
                    alert_data.get('severity', 'info'),
                    alert_data.get('gpu_index'),
                    alert_data.get('value'),
                    alert_data.get('threshold')
                ))

                conn.commit()
                logger.debug(f"Stored alert: {alert_data.get('message', '')}")

        except Exception as e:
            logger.error(f"Error storing alert: {e}")

    def get_gpu_metrics_history(self, hours: int = 24, gpu_index: int | None = None, metric_type: str = "all") -> list[dict]:
        """Get GPU metrics history."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cutoff_time = (datetime.now() - timedelta(hours=hours)).timestamp()

                # Build query based on metric type
                if metric_type == "all":
                    if gpu_index is not None:
                        cursor.execute('''
                            SELECT * FROM gpu_metrics
                            WHERE timestamp >= ? AND gpu_index = ?
                            ORDER BY timestamp DESC
                            LIMIT 1000
                        ''', (cutoff_time, gpu_index))
                    else:
                        cursor.execute('''
                            SELECT * FROM gpu_metrics
                            WHERE timestamp >= ?
                            ORDER BY timestamp DESC
                            LIMIT 1000
                        ''', (cutoff_time,))
                else:
                    # Select specific metric columns
                    metric_columns = {
                        "utilization": "gpu_utilization_percent",
                        "memory_used_mb": "memory_used_mb",
                        "memory_total_mb": "memory_total_mb",
                        "memory_free_mb": "memory_free_mb",
                        "memory_utilization_percent": "memory_utilization_percent",
                        "temperature_celsius": "temperature_celsius",
                        "fan_speed_percent": "fan_speed_percent",
                        "power_draw_watts": "power_draw_watts",
                        "power_limit_watts": "power_limit_watts"
                    }

                    column_name = metric_columns.get(metric_type, "gpu_utilization_percent")

                    if gpu_index is not None:
                        cursor.execute(f'''
                            SELECT timestamp, gpu_index, {column_name}
                            FROM gpu_metrics
                            WHERE timestamp >= ? AND gpu_index = ? AND {column_name} IS NOT NULL
                            ORDER BY timestamp DESC
                            LIMIT 1000
                        ''', (cutoff_time, gpu_index))
                    else:
                        cursor.execute(f'''
                            SELECT timestamp, gpu_index, {column_name}
                            FROM gpu_metrics
                            WHERE timestamp >= ? AND {column_name} IS NOT NULL
                            ORDER BY timestamp DESC
                            LIMIT 1000
                        ''', (cutoff_time,))

                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                return [dict(zip(columns, row, strict=False)) for row in rows]

        except Exception as e:
            logger.error(f"Error retrieving GPU metrics history: {e}")
            return []

    def get_agent_allocation_history(self, hours: int = 24, agent_name: str | None = None) -> list[dict]:
        """Get agent allocation history."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cutoff_time = (datetime.now() - timedelta(hours=hours)).timestamp()

                if agent_name:
                    cursor.execute('''
                        SELECT * FROM agent_allocations
                        WHERE timestamp >= ? AND agent_name = ?
                        ORDER BY timestamp DESC
                        LIMIT 500
                    ''', (cutoff_time, agent_name))
                else:
                    cursor.execute('''
                        SELECT * FROM agent_allocations
                        WHERE timestamp >= ?
                        ORDER BY timestamp DESC
                        LIMIT 500
                    ''', (cutoff_time,))

                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                return [dict(zip(columns, row, strict=False)) for row in rows]

        except Exception as e:
            logger.error(f"Error retrieving agent allocation history: {e}")
            return []

    def get_performance_trends(self, hours: int = 24) -> dict[str, list]:
        """Get performance trends data."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cutoff_time = (datetime.now() - timedelta(hours=hours)).timestamp()

                cursor.execute('''
                    SELECT timestamp, metric_name, metric_value
                    FROM performance_metrics
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                    LIMIT 2000
                ''', (cutoff_time,))

                rows = cursor.fetchall()

                # Group by metric name
                trends = {}
                timestamps = set()

                for row in rows:
                    timestamp, metric_name, value = row
                    timestamps.add(timestamp)

                    if metric_name not in trends:
                        trends[metric_name] = []
                    trends[metric_name].append((timestamp, value))

                # Sort timestamps and align data
                sorted_timestamps = sorted(timestamps)

                result = {'timestamps': sorted_timestamps}
                for metric_name, data_points in trends.items():
                    # Create aligned data array
                    aligned_data = []
                    data_dict = dict(data_points)

                    for ts in sorted_timestamps:
                        aligned_data.append(data_dict.get(ts))

                    result[metric_name] = aligned_data

                return result

        except Exception as e:
            logger.error(f"Error retrieving performance trends: {e}")
            return {'timestamps': [], 'error': str(e)}

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Get recent alerts."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT * FROM alerts
                    WHERE resolved = FALSE
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))

                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                return [dict(zip(columns, row, strict=False)) for row in rows]

        except Exception as e:
            logger.error(f"Error retrieving recent alerts: {e}")
            return []

    def resolve_alert(self, alert_id: int):
        """Mark an alert as resolved."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    UPDATE alerts
                    SET resolved = TRUE, resolved_at = ?
                    WHERE id = ?
                ''', (datetime.now().timestamp(), alert_id))

                conn.commit()
                logger.debug(f"Resolved alert ID: {alert_id}")

        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {e}")

    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to prevent database bloat."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cutoff_time = (datetime.now() - timedelta(days=days_to_keep)).timestamp()

                # Delete old records
                tables = ['gpu_metrics', 'agent_allocations', 'performance_metrics', 'alerts']
                total_deleted = 0

                for table in tables:
                    cursor.execute(f'DELETE FROM {table} WHERE timestamp < ?', (cutoff_time,))
                    deleted = cursor.rowcount
                    total_deleted += deleted
                    logger.debug(f"Deleted {deleted} old records from {table}")

                conn.commit()
                logger.info(f"Cleaned up {total_deleted} old records from database")

        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")

    def get_storage_stats(self) -> dict:
        """Get database storage statistics."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                stats = {}

                # Get record counts
                tables = ['gpu_metrics', 'agent_allocations', 'performance_metrics', 'alerts']
                for table in tables:
                    cursor.execute(f'SELECT COUNT(*) FROM {table}')
                    stats[f'{table}_count'] = cursor.fetchone()[0]

                # Get database file size
                if os.path.exists(self.db_path):
                    stats['db_size_bytes'] = os.path.getsize(self.db_path)
                    stats['db_size_mb'] = stats['db_size_bytes'] / (1024 * 1024)

                return stats

        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {}

# Global storage instance
_storage_instance: DashboardStorage | None = None

def get_storage() -> DashboardStorage:
    """Get the global storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = DashboardStorage()
    return _storage_instance
