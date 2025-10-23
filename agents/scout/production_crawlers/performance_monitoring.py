#!/usr/bin/env python3
"""
Performance Monitoring for Unified Production Crawler

PHASE 3 ENHANCEMENT: Comprehensive performance tracking and metrics collection
for the unified production crawler with real-time monitoring and optimization.
"""

import asyncio
import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from common.observability import get_logger

logger = get_logger(__name__)


class PerformanceMetrics:
    """Real-time performance metrics collection and analysis"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.start_time = time.time()

        # Core metrics
        self.articles_processed = 0
        self.articles_successful = 0
        self.sites_crawled = 0
        self.errors_total = 0

        # Strategy metrics
        self.strategy_usage = defaultdict(int)
        self.strategy_performance = defaultdict(list)

        # Time-based metrics
        self.processing_times = deque(maxlen=max_history)
        self.articles_per_second_history = deque(maxlen=max_history)
        self.error_rate_history = deque(maxlen=max_history)

        # Site-specific metrics
        self.site_metrics = defaultdict(lambda: {
            'articles_found': 0,
            'articles_successful': 0,
            'processing_times': [],
            'last_crawl': None,
            'strategy_used': None
        })

        # Real-time monitoring
        self.monitoring_active = False
        self.monitoring_thread = None

    def record_crawl_start(self, site_config, strategy: str):
        """Record the start of a crawl operation"""
        site_key = f"{site_config.domain}_{site_config.source_id or 'unknown'}"
        self.site_metrics[site_key]['last_crawl'] = time.time()
        self.site_metrics[site_key]['strategy_used'] = strategy
        self.strategy_usage[strategy] += 1

    def record_crawl_complete(self, site_config, articles_found: int,
                            articles_successful: int, processing_time: float):
        """Record the completion of a crawl operation"""
        site_key = f"{site_config.domain}_{site_config.source_id or 'unknown'}"

        # Update totals
        self.articles_processed += articles_found
        self.articles_successful += articles_successful
        self.sites_crawled += 1

        # Update site metrics
        self.site_metrics[site_key]['articles_found'] += articles_found
        self.site_metrics[site_key]['articles_successful'] += articles_successful
        self.site_metrics[site_key]['processing_times'].append(processing_time)

        # Update time-based metrics
        self.processing_times.append(processing_time)
        if processing_time > 0:
            articles_per_second = articles_found / processing_time
            self.articles_per_second_history.append(articles_per_second)

        # Update strategy performance
        strategy = self.site_metrics[site_key]['strategy_used']
        if strategy:
            self.strategy_performance[strategy].append(articles_per_second)

    def record_error(self, error_type: str = "unknown"):
        """Record an error occurrence"""
        self.errors_total += 1

        # Update error rate history
        current_time = time.time()
        total_runtime = current_time - self.start_time
        if total_runtime > 0:
            error_rate = self.errors_total / total_runtime
            self.error_rate_history.append(error_rate)

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        current_time = time.time()
        total_runtime = current_time - self.start_time

        # Calculate rates
        articles_per_second = self.articles_processed / total_runtime if total_runtime > 0 else 0
        success_rate = self.articles_successful / self.articles_processed if self.articles_processed > 0 else 0
        error_rate = self.errors_total / total_runtime if total_runtime > 0 else 0

        # Strategy analysis
        strategy_summary = {}
        for strategy, performances in self.strategy_performance.items():
            if performances:
                strategy_summary[strategy] = {
                    'usage_count': self.strategy_usage[strategy],
                    'avg_performance': sum(performances) / len(performances),
                    'best_performance': max(performances),
                    'worst_performance': min(performances)
                }

        return {
            "timestamp": datetime.now().isoformat(),
            "total_runtime_seconds": total_runtime,
            "articles_processed": self.articles_processed,
            "articles_successful": self.articles_successful,
            "sites_crawled": self.sites_crawled,
            "errors_total": self.errors_total,
            "articles_per_second": articles_per_second,
            "success_rate": success_rate,
            "error_rate": error_rate,
            "strategy_summary": strategy_summary,
            "site_metrics": dict(self.site_metrics)
        }

    def get_recent_performance(self, window_seconds: int = 300) -> Dict[str, Any]:
        """Get performance metrics for recent time window"""
        current_time = time.time()
        window_start = current_time - window_seconds

        # Filter recent processing times
        recent_times = [t for t in self.processing_times if (current_time - t) <= window_seconds]
        recent_aps = [aps for aps in self.articles_per_second_history if (current_time - aps) <= window_seconds]

        return {
            "window_seconds": window_seconds,
            "recent_processing_times": recent_times,
            "avg_processing_time": sum(recent_times) / len(recent_times) if recent_times else 0,
            "recent_articles_per_second": recent_aps,
            "avg_articles_per_second": sum(recent_aps) / len(recent_aps) if recent_aps else 0,
            "processing_count": len(recent_times)
        }

    def get_site_performance_report(self) -> List[Dict[str, Any]]:
        """Get performance report for each site"""
        report = []

        for site_key, metrics in self.site_metrics.items():
            processing_times = metrics['processing_times']
            if processing_times:
                avg_time = sum(processing_times) / len(processing_times)
                total_articles = metrics['articles_found']
                success_rate = metrics['articles_successful'] / total_articles if total_articles > 0 else 0

                report.append({
                    "site_key": site_key,
                    "total_articles": total_articles,
                    "successful_articles": metrics['articles_successful'],
                    "success_rate": success_rate,
                    "avg_processing_time": avg_time,
                    "articles_per_second": total_articles / sum(processing_times) if sum(processing_times) > 0 else 0,
                    "crawl_count": len(processing_times),
                    "last_strategy": metrics['strategy_used'],
                    "last_crawl": metrics['last_crawl']
                })

        # Sort by performance (articles per second)
        report.sort(key=lambda x: x['articles_per_second'], reverse=True)
        return report

    def start_monitoring(self, interval_seconds: int = 60):
        """Start background performance monitoring"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval_seconds,),
            daemon=True
        )
        self.monitoring_thread.start()
        logger.info("✅ Performance monitoring started")

    def stop_monitoring(self):
        """Stop background performance monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("🛑 Performance monitoring stopped")

    def _monitoring_loop(self, interval_seconds: int):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                metrics = self.get_current_metrics()
                logger.info(f"📊 Performance: {metrics['articles_per_second']:.2f} articles/sec, "
                          f"Success: {metrics['success_rate']:.1%}, "
                          f"Sites: {metrics['sites_crawled']}")

                # Log strategy performance
                for strategy, perf in metrics['strategy_summary'].items():
                    logger.debug(f"🎯 {strategy}: {perf['avg_performance']:.2f} articles/sec "
                               f"({perf['usage_count']} uses)")

            except Exception as e:
                logger.error(f"Error in performance monitoring: {e}")

            time.sleep(interval_seconds)

    def export_metrics(self, filepath: str):
        """Export comprehensive metrics to JSON file"""
        metrics = {
            "export_timestamp": datetime.now().isoformat(),
            "current_metrics": self.get_current_metrics(),
            "recent_performance": self.get_recent_performance(),
            "site_performance_report": self.get_site_performance_report(),
            "raw_data": {
                "processing_times": list(self.processing_times),
                "articles_per_second_history": list(self.articles_per_second_history),
                "error_rate_history": list(self.error_rate_history)
            }
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(metrics, f, indent=2, default=str)
            logger.info(f"✅ Performance metrics exported to {filepath}")

        except Exception as e:
            logger.error(f"❌ Failed to export metrics: {e}")


class PerformanceOptimizer:
    """Performance optimization recommendations based on metrics"""

    def __init__(self, metrics: PerformanceMetrics):
        self.metrics = metrics

    def get_optimization_recommendations(self) -> List[str]:
        """Get optimization recommendations based on current performance"""
        recommendations = []

        current_metrics = self.metrics.get_current_metrics()

        # Articles per second analysis
        aps = current_metrics['articles_per_second']
        if aps < 0.5:
            recommendations.append("⚠️ Low throughput detected. Consider increasing concurrent_sites or optimizing strategies.")
        elif aps > 5.0:
            recommendations.append("✅ Excellent throughput! Current configuration is highly optimized.")

        # Success rate analysis
        success_rate = current_metrics['success_rate']
        if success_rate < 0.7:
            recommendations.append("⚠️ Low success rate detected. Check for site blocking or content extraction issues.")
        elif success_rate > 0.9:
            recommendations.append("✅ High success rate! Content extraction is working well.")

        # Strategy analysis
        strategy_summary = current_metrics['strategy_summary']
        if strategy_summary:
            best_strategy = max(strategy_summary.items(), key=lambda x: x[1]['avg_performance'])
            recommendations.append(f"🎯 Best performing strategy: {best_strategy[0]} "
                                f"({best_strategy[1]['avg_performance']:.2f} articles/sec)")

            # Check strategy balance
            total_usage = sum(s['usage_count'] for s in strategy_summary.values())
            for strategy, stats in strategy_summary.items():
                usage_pct = stats['usage_count'] / total_usage if total_usage > 0 else 0
                if usage_pct < 0.1 and stats['avg_performance'] > aps * 1.2:
                    recommendations.append(f"💡 Underutilized high-performance strategy: {strategy}. "
                                        "Consider adjusting site assignments.")

        # Error rate analysis
        error_rate = current_metrics['error_rate']
        if error_rate > 0.1:  # More than 1 error per 10 seconds
            recommendations.append("⚠️ High error rate detected. Check logs for recurring issues.")

        # Site-specific recommendations
        site_report = self.metrics.get_site_performance_report()
        slow_sites = [s for s in site_report if s['articles_per_second'] < 0.5]
        if slow_sites:
            recommendations.append(f"🐌 {len(slow_sites)} sites performing slowly. "
                                "Consider switching to ultra_fast strategy or excluding from crawl.")

        return recommendations

    def suggest_configuration_changes(self) -> Dict[str, Any]:
        """Suggest configuration changes for optimization"""
        suggestions = {}

        current_metrics = self.metrics.get_current_metrics()
        aps = current_metrics['articles_per_second']

        # Concurrent sites suggestion
        if aps < 1.0:
            suggestions['concurrent_sites'] = min(5, self.metrics.sites_crawled + 1)
        elif aps > 3.0:
            suggestions['concurrent_sites'] = max(2, self.metrics.sites_crawled - 1)

        # Articles per site suggestion
        if aps < 0.8:
            suggestions['articles_per_site'] = max(10, current_metrics.get('articles_per_site', 25) - 5)
        elif aps > 2.0:
            suggestions['articles_per_site'] = min(50, current_metrics.get('articles_per_site', 25) + 5)

        # Strategy preferences
        strategy_summary = current_metrics['strategy_summary']
        if strategy_summary:
            best_strategy = max(strategy_summary.items(), key=lambda x: x[1]['avg_performance'])
            suggestions['preferred_strategy'] = best_strategy[0]

        return suggestions


# Global performance monitoring instance
_performance_monitor = PerformanceMetrics()

def get_performance_monitor() -> PerformanceMetrics:
    """Get the global performance monitor instance"""
    return _performance_monitor

def start_performance_monitoring(interval_seconds: int = 60):
    """Start global performance monitoring"""
    _performance_monitor.start_monitoring(interval_seconds)

def stop_performance_monitoring():
    """Stop global performance monitoring"""
    _performance_monitor.stop_monitoring()

def export_performance_metrics(filepath: str):
    """Export current performance metrics"""
    _performance_monitor.export_metrics(filepath)

# Export for unified crawler integration
__all__ = [
    'PerformanceMetrics',
    'PerformanceOptimizer',
    'get_performance_monitor',
    'start_performance_monitoring',
    'stop_performance_monitoring',
    'export_performance_metrics'
]
