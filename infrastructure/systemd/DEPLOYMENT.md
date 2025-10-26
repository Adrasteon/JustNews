---
title: Systemd Deployment Overview
description: Canonical entry-point for deploying and restarting JustNews with systemd
---

# Systemd Deployment – Quick Start

## TL;DR: One-command fresh restart (recommended)

```
sudo ./infrastructure/systemd/reset_and_start.sh
```

What it does:
- Stops/disables all services, frees ports, reloads systemd if needed
- Ensures GPU Orchestrator is READY before any agents start
- Starts MCP Bus, then all agents in order, then runs health check

## Manual sequence (orchestrator-first)

```
sudo systemctl enable --now justnews@gpu_orchestrator
curl -fsS http://127.0.0.1:8014/ready
sudo ./infrastructure/systemd/scripts/enable_all.sh start
sudo ./infrastructure/systemd/scripts/health_check.sh
```

Notes:
- `enable_all.sh` supports `fresh` and `--fresh` alias and now starts `gpu_orchestrator` first, waiting for `/ready`.
- Adjust gating timeout via drop-in: `Environment=GATE_TIMEOUT=300`.
Content ingestion automation (`justnews-crawl-scheduler.timer`, `justnews@cluster_pipeline.service`, `justnews@fact_intel.service`) remains disabled by default; enable each only after verifying Stage A health:

```
sudo systemctl enable --now justnews-crawl-scheduler.timer
sudo systemctl enable --now justnews@cluster_pipeline
sudo systemctl enable --now justnews@fact_intel
```

Enable `justnews@cluster_pipeline` only after fact intelligence services (e.g., `justnews@fact_intel`) have run successfully; the clustering stage consumes Grounded Truth scores emitted by the fact pipeline.

The crawl scheduler service (`justnews-crawl-scheduler.service`) is a oneshot wrapper around `scripts/ops/run_crawl_schedule.py`. Override paths or crawler URL via `/etc/justnews/crawl_scheduler.env`; Prometheus textfile metrics default to `logs/analytics/crawl_scheduler.prom` unless `CRAWL_SCHEDULER_METRICS` is set.

These services rely on the configuration described in `docs/operations/systemd-baseline-then-k8s-phased-plan.md`.

## Related documentation
- Quick Reference: `infrastructure/systemd/QUICK_REFERENCE.md`
- Comprehensive Guide: `infrastructure/systemd/COMPREHENSIVE_SYSTEMD_GUIDE.md`
- PostgreSQL Integration: `infrastructure/systemd/postgresql_integration.md`

