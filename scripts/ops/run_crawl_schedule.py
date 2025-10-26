#!/usr/bin/env python3
"""Stage B1 crawl scheduler entry-point.

This module orchestrates automated crawl runs by reading
`config/crawl_schedule.yaml`, selecting the runs that are due for the current
window, and invoking the crawler agent sequentially with guarded article
budgets. It is designed to execute from a systemd timer (hourly cadence by
default) but also supports ad-hoc invocations for QA using the `--dry-run`
flag.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is importable when executed as a standalone script
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests
from prometheus_client import CollectorRegistry, Gauge, write_to_textfile

from agents.crawler_control.crawl_schedule import (
    CrawlRun,
    CrawlSchedule,
    CrawlScheduleError,
    load_crawl_schedule,
)
from common.metrics import JustNewsMetrics

DEFAULT_SCHEDULE_PATH = Path("config/crawl_schedule.yaml")
DEFAULT_STATE_PATH = Path("logs/analytics/crawl_scheduler_state.json")
DEFAULT_SUCCESS_PATH = Path("logs/analytics/crawl_scheduler_success.json")
DEFAULT_METRICS_OUTPUT = Path("logs/analytics/crawl_scheduler.prom")
DEFAULT_CRAWLER_URL = "http://127.0.0.1:8015"
DEFAULT_CRAWLER_POLL_INTERVAL = 5.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Stage B1 crawl schedule")
    parser.add_argument(
        "--schedule",
        type=Path,
        default=DEFAULT_SCHEDULE_PATH,
        help="Path to crawl schedule YAML (default: config/crawl_schedule.yaml)",
    )
    parser.add_argument(
        "--state-output",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="Path to write scheduler state JSON for governance logs",
    )
    parser.add_argument(
        "--success-output",
        type=Path,
        default=DEFAULT_SUCCESS_PATH,
        help="Path to append summary of successful executions",
    )
    parser.add_argument(
        "--crawler-url",
        default=DEFAULT_CRAWLER_URL,
        help="Crawler agent base URL (default: http://127.0.0.1:8015)",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=DEFAULT_METRICS_OUTPUT,
        help="Path to write Prometheus textfile metrics",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not invoke the crawler endpoint; print planned actions only",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not sleep until minute offsets; trigger immediately",
    )
    parser.add_argument(
        "--max-target",
        type=int,
        default=None,
        help="Override target articles per hour budget",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Override HTTP timeout for crawl requests",
    )
    return parser.parse_args()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sleep_until(target: datetime) -> None:
    now = _now()
    delay = (target - now).total_seconds()
    if delay > 1:
        time.sleep(delay)


def _effective_limit(remaining: int, run: CrawlRun) -> int:
    if remaining <= 0:
        return 0

    domains = max(len(run.domains), 1)
    per_site_cap = run.max_articles_per_site or remaining

    if per_site_cap * domains <= remaining:
        return per_site_cap

    limit = remaining // domains
    return limit if limit > 0 else 0


def _build_payload(run: CrawlRun, max_articles: int, timeout_seconds: int, strategy: str, enable_ai: bool) -> Dict[str, Any]:
    concurrency = run.concurrent_sites
    kwargs = {
        "max_articles_per_site": max_articles,
        "concurrent_sites": concurrency,
        "strategy": strategy,
        "enable_ai": enable_ai,
        "timeout": timeout_seconds,
        "schedule_name": run.name,
        "priority": run.priority,
        "max_sites": len(run.domains),
    }
    return {"args": [run.domains], "kwargs": kwargs}


def _await_job(base_url: str, job_id: str, timeout_seconds: int) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    status_url = f"{base_url}/job_status/{job_id}"

    while True:
        try:
            response = requests.get(status_url, timeout=10)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to fetch job status for {job_id}: {exc}") from exc

        status = payload.get("status")
        if status in {"completed", "failed"}:
            return payload

        if time.time() >= deadline:
            raise TimeoutError(f"Job {job_id} exceeded timeout {timeout_seconds}s")

        time.sleep(DEFAULT_CRAWLER_POLL_INTERVAL)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _append_success(path: Path, entry: Dict[str, Any]) -> None:
    _ensure_parent(path)
    if not path.exists():
        history: List[Dict[str, Any]] = []
    else:
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    history.append(entry)
    path.write_text(json.dumps(history[-200:], indent=2), encoding="utf-8")


def _init_metrics() -> tuple[CollectorRegistry, Dict[str, Gauge]]:
    registry = CollectorRegistry()
    JustNewsMetrics("crawler_scheduler", registry=registry)
    gauges = {
        "domains": Gauge(
            "justnews_crawler_scheduler_domains_crawled_total",
            "Domains crawled during this scheduler window",
            registry=registry,
        ),
        "articles": Gauge(
            "justnews_crawler_scheduler_articles_accepted_total",
            "Articles accepted during this scheduler window",
            registry=registry,
        ),
        "lag": Gauge(
            "justnews_crawler_scheduler_lag_seconds",
            "Lag between scheduled and actual crawl start",
            registry=registry,
        ),
        "timestamp": Gauge(
            "justnews_crawler_scheduler_last_successful_run_timestamp",
            "Unix timestamp of last successful crawl batch",
            registry=registry,
        ),
    }
    return registry, gauges


def main() -> int:
    args = _parse_args()

    try:
        schedule: CrawlSchedule = load_crawl_schedule(args.schedule)
    except CrawlScheduleError as exc:
        print(f"[scheduler] failed to load schedule: {exc}", file=sys.stderr)
        return 2

    reference_time = _now()
    due_runs = schedule.due_runs(reference_time)
    if not due_runs:
        print("[scheduler] no runs due for this window")
        return 0

    target_articles = args.max_target or schedule.global_config.target_articles_per_hour
    remaining_articles = max(target_articles, 0)
    timeout_seconds = args.timeout or schedule.global_config.default_timeout_seconds

    registry, gauges = _init_metrics()
    total_domains = 0
    total_articles = 0
    worst_lag = 0.0
    last_success_epoch: Optional[float] = None
    run_results: List[Dict[str, Any]] = []

    for run in due_runs:
        scheduled_start = run.scheduled_start(reference_time)

        if remaining_articles <= 0:
            run_results.append(
                {
                    "name": run.name,
                    "status": "skipped",
                    "reason": "article budget exhausted",
                    "scheduled_start": scheduled_start.isoformat(),
                }
            )
            continue

        effective_limit = _effective_limit(remaining_articles, run)
        if effective_limit <= 0:
            run_results.append(
                {
                    "name": run.name,
                    "status": "skipped",
                    "reason": "insufficient article budget per site",
                    "scheduled_start": scheduled_start.isoformat(),
                }
            )
            continue

        if not args.no_wait and not args.dry_run:
            _sleep_until(scheduled_start)

        run_start = _now()
        lag_seconds = max((run_start - scheduled_start).total_seconds(), 0.0)
        worst_lag = max(worst_lag, lag_seconds)

        payload = _build_payload(
            run,
            max_articles=effective_limit,
            timeout_seconds=timeout_seconds,
            strategy=schedule.global_config.strategy,
            enable_ai=schedule.global_config.enable_ai_enrichment,
        )

        result: Dict[str, Any]
        status: str
        message: Optional[str] = None

        if args.dry_run:
            status = "dry-run"
            result = {
                "domains": run.domains,
                "max_articles_per_site": effective_limit,
                "concurrent_sites": run.concurrent_sites,
            }
        else:
            try:
                submit_url = f"{args.crawler_url.rstrip('/')}/unified_production_crawl"
                response = requests.post(submit_url, json=payload, timeout=timeout_seconds)
                response.raise_for_status()
                submission = response.json()
                job_id = submission.get("job_id")
                if not job_id:
                    raise RuntimeError("Crawler response missing job_id")
                job_payload = _await_job(args.crawler_url.rstrip('/'), job_id, timeout_seconds)
                result = job_payload.get("result") or {}
                status = job_payload.get("status", "unknown")
                if status != "completed":
                    message = job_payload.get("error") or job_payload.get("message")
            except requests.RequestException as exc:
                status = "failed"
                message = str(exc)
                result = {}
            except TimeoutError as exc:
                status = "failed"
                message = str(exc)
                result = {}
            except RuntimeError as exc:
                status = "failed"
                message = str(exc)
                result = {}

        domains_count = len(run.domains)
        articles_count = int(result.get("articles_ingested", result.get("articles", 0))) if status == "completed" else 0

        if status == "completed":
            remaining_articles = max(remaining_articles - (articles_count or (effective_limit * domains_count)), 0)
            total_domains += domains_count
            total_articles += articles_count
            last_success_epoch = run_start.timestamp()
        elif status == "dry-run":
            total_domains += domains_count
            # No budget changes during dry run
        else:
            # For failed runs we do not deduct the budget to allow retry on next iteration
            pass

        run_results.append(
            {
                "name": run.name,
                "status": status,
                "scheduled_start": scheduled_start.isoformat(),
                "started_at": run_start.isoformat(),
                "lag_seconds": lag_seconds,
                "domains": run.domains,
                "max_articles_per_site": effective_limit,
                "result": result,
                "message": message,
            }
        )

    gauges["domains"].set(total_domains)
    gauges["articles"].set(total_articles)
    gauges["lag"].set(worst_lag)
    if last_success_epoch is not None:
        gauges["timestamp"].set(last_success_epoch)

    if args.metrics_output:
        _ensure_parent(args.metrics_output)
        write_to_textfile(args.metrics_output, registry)

    state_payload = {
        "executed_at": reference_time.isoformat(),
        "runs": run_results,
        "governance": schedule.governance,
        "target_articles": target_articles,
        "remaining_articles": remaining_articles,
        "dry_run": args.dry_run,
        "crawler_url": args.crawler_url,
    }
    _write_json(args.state_output, state_payload)

    successful = [run for run in run_results if run["status"] == "completed"]
    if successful:
        summary_entry = {
            "timestamp": reference_time.isoformat(),
            "runs": [
                {
                    "name": run["name"],
                    "domains": run["domains"],
                    "articles": run["result"].get("articles_ingested") if isinstance(run.get("result"), dict) else None,
                }
                for run in successful
            ],
            "total_articles": total_articles,
            "total_domains": total_domains,
        }
        _append_success(args.success_output, summary_entry)

    failed_runs = [run for run in run_results if run["status"] == "failed"]
    if failed_runs:
        print("[scheduler] one or more runs failed", file=sys.stderr)
        for run in failed_runs:
            print(f"  - {run['name']}: {run.get('message')}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
