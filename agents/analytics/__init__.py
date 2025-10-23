"""
Analytics Integration Module for JustNewsAgent

Integrates the advanced analytics engine with existing GPU metrics
and provides utilities for starting analytics services.
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from ..common.advanced_analytics import PerformanceMetrics, get_analytics_engine
from ..common.gpu_metrics import end_event, start_event


class AnalyticsIntegration:
    """
    Integration layer between existing GPU metrics and advanced analytics engine
    """

    def __init__(self):
        self.analytics_engine = get_analytics_engine()
        self.active_events = {}  # Track active GPU events
        self.integration_active = False

    def start_integration(self):
        """Start the analytics integration"""
        if self.integration_active:
            return

        self.integration_active = True
        self.analytics_engine.start()

        # Start background thread to sync GPU events
        self.sync_thread = threading.Thread(target=self._sync_gpu_events, daemon=True)
        self.sync_thread.start()

        print("🚀 Analytics integration started")

    def stop_integration(self):
        """Stop the analytics integration"""
        self.integration_active = False
        self.analytics_engine.stop()
        print("🛑 Analytics integration stopped")

    def _sync_gpu_events(self):
        """Background thread to sync GPU events from logs to analytics engine"""
        gpu_events_file = Path(__file__).parent.parent.parent / "logs" / "gpu_events.jsonl"

        if not gpu_events_file.exists():
            return

        last_position = 0

        while self.integration_active:
            try:
                if gpu_events_file.exists():
                    with open(gpu_events_file) as f:
                        f.seek(last_position)
                        new_lines = f.readlines()
                        last_position = f.tell()

                    for line in new_lines:
                        if line.strip():
                            try:
                                event_data = json.loads(line.strip())
                                self._process_gpu_event(event_data)
                            except json.JSONDecodeError:
                                continue

                time.sleep(5)  # Check every 5 seconds

            except Exception as e:
                print(f"Error syncing GPU events: {e}")
                time.sleep(10)

    def _process_gpu_event(self, event_data: dict[str, Any]):
        """Process a GPU event and convert to analytics metric"""
        try:
            meta = event_data.get('meta', {})
            torch_memory = event_data.get('torch_memory', [{}])

            # Extract GPU memory info
            gpu_memory = torch_memory[0] if torch_memory else {}
            gpu_memory_allocated_mb = gpu_memory.get('memory_allocated_mb', 0.0)
            gpu_memory_reserved_mb = gpu_memory.get('memory_reserved_mb', 0.0)

            # Extract nvidia-smi data if available
            nvidia_smi = event_data.get('nvidia_smi', {})
            gpu_utilization_pct = nvidia_smi.get('utilization_gpu_pct')
            temperature_c = nvidia_smi.get('temperature_c')
            power_draw_w = nvidia_smi.get('power_draw_w')

            # Calculate throughput if batch_size and processing_time available
            batch_size = meta.get('batch_size', 1)
            processing_time_s = event_data.get('processing_time_s', 0.0)
            throughput_items_per_s = batch_size / processing_time_s if processing_time_s > 0 else 0.0

            # Create analytics metric
            metric = PerformanceMetrics(
                timestamp=datetime.fromisoformat(event_data.get('written_at', datetime.now().isoformat())),
                agent_name=meta.get('agent', 'unknown'),
                operation=meta.get('operation', 'unknown'),
                processing_time_s=processing_time_s,
                batch_size=batch_size,
                success=event_data.get('success', False),
                gpu_memory_allocated_mb=gpu_memory_allocated_mb,
                gpu_memory_reserved_mb=gpu_memory_reserved_mb,
                gpu_utilization_pct=gpu_utilization_pct or 0.0,
                temperature_c=temperature_c or 0.0,
                power_draw_w=power_draw_w or 0.0,
                throughput_items_per_s=throughput_items_per_s
            )

            # Record in analytics engine
            self.analytics_engine.record_metric(metric)

        except Exception as e:
            print(f"Error processing GPU event: {e}")

    def enhanced_start_event(self, **meta) -> str:
        """Enhanced start_event that also integrates with analytics"""
        event_id = start_event(**meta)
        self.active_events[event_id] = meta
        return event_id

    def enhanced_end_event(self, event_id: str, **outcome):
        """Enhanced end_event that also records analytics"""
        # Call original end_event
        result = end_event(event_id, **outcome)

        # Also record in analytics engine
        try:
            meta = self.active_events.pop(event_id, {})
            torch_memory = result.get('torch_memory', [{}])

            gpu_memory = torch_memory[0] if torch_memory else {}
            nvidia_smi = result.get('nvidia_smi', {})

            batch_size = meta.get('batch_size', 1)
            processing_time_s = outcome.get('processing_time_s', 0.0)
            throughput = batch_size / processing_time_s if processing_time_s > 0 else 0.0

            metric = PerformanceMetrics(
                timestamp=datetime.now(),
                agent_name=meta.get('agent', 'unknown'),
                operation=meta.get('operation', 'unknown'),
                processing_time_s=processing_time_s,
                batch_size=batch_size,
                success=outcome.get('success', False),
                gpu_memory_allocated_mb=gpu_memory.get('memory_allocated_mb', 0.0),
                gpu_memory_reserved_mb=gpu_memory.get('memory_reserved_mb', 0.0),
                gpu_utilization_pct=nvidia_smi.get('utilization_gpu_pct') or 0.0,
                temperature_c=nvidia_smi.get('temperature_c') or 0.0,
                power_draw_w=nvidia_smi.get('power_draw_w') or 0.0,
                throughput_items_per_s=throughput
            )

            self.analytics_engine.record_metric(metric)

        except Exception as e:
            print(f"Error recording analytics metric: {e}")

        return result

# Global integration instance
analytics_integration = AnalyticsIntegration()

def get_analytics_integration() -> AnalyticsIntegration:
    """Get the global analytics integration instance"""
    return analytics_integration

def start_analytics_integration():
    """Start the analytics integration"""
    analytics_integration.start_integration()

def stop_analytics_integration():
    """Stop the analytics integration"""
    analytics_integration.stop_integration()

# Enhanced GPU metrics functions
def enhanced_start_event(**meta) -> str:
    """Enhanced start_event with analytics integration"""
    return analytics_integration.enhanced_start_event(**meta)

def enhanced_end_event(event_id: str, **outcome):
    """Enhanced end_event with analytics integration"""
    return analytics_integration.enhanced_end_event(event_id, **outcome)

# Convenience functions for starting analytics services
def start_analytics_dashboard(host: str = "0.0.0.0", port: int = 8012):
    """Start the analytics dashboard"""
    from .dashboard import start_analytics_dashboard as _start_dashboard
    _start_dashboard(host, port)

def start_all_analytics_services(host: str = "0.0.0.0", dashboard_port: int = 8012):
    """Start all analytics services (integration + dashboard)"""
    print("🚀 Starting JustNewsAgent Advanced Analytics Services...")

    # Start integration
    start_analytics_integration()

    # Start dashboard in background
    import threading
    dashboard_thread = threading.Thread(
        target=start_analytics_dashboard,
        args=(host, dashboard_port),
        daemon=True
    )
    dashboard_thread.start()

    print(f"📊 Analytics Dashboard: http://{host}:{dashboard_port}")
    print("✅ All analytics services started successfully")

    return dashboard_thread

if __name__ == "__main__":
    # Start all analytics services
    start_all_analytics_services()
