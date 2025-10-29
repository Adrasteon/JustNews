---
title: JustNews systemd deployment – operator index
description: Practical entry point for native (systemd) operations
---

# JustNews native deployment (systemd) – operator index

This directory contains the native (no Docker/K8s) deployment scaffold for running the MCP bus and all agents as systemd instanced units.

## Quick operator flow (5 minutes)

1) Start GPU Orchestrator first (satisfies ExecStartPre model gating):
	 - `sudo systemctl enable --now justnews@gpu_orchestrator`
	 - Wait for READY: `curl -fsS http://127.0.0.1:8014/ready` → HTTP 200

2) Start the rest in order:
	 - `sudo ./infrastructure/systemd/scripts/enable_all.sh start`

3) Check health:
	 - `sudo ./infrastructure/systemd/scripts/health_check.sh`

Troubleshooting? See the Quick Reference and Comprehensive guide below.

If the synthesizer service remains degraded, confirm the dashboard-hosted transparency endpoint is reachable:
`curl -fsS http://127.0.0.1:8013/transparency/status | jq '.integrity.status'`. Analytics health should report `{"status":"healthy"}` via `curl -fsS http://127.0.0.1:8011/health`.

## Documents

- Quick Reference (copy-paste commands, port map, troubleshooting)
	- `./QUICK_REFERENCE.md`
- Comprehensive systemd guide (gating internals, drop-ins, tuning)
	- `./COMPREHENSIVE_SYSTEMD_GUIDE.md`
- PostgreSQL integration guide (DB URL and checks)
	- `./postgresql_integration.md`

Incident reference:
- Systemd Orchestrator Incident Report — Sept 13, 2025
	- `../../markdown_docs/development_reports/systemd_operational_incident_report_2025-09-13.md`

## Scripts

- `enable_all.sh` – enable/disable/start/stop/restart/fresh for all services
- `health_check.sh` – table view of systemd/port/HTTP/READY status
- `preflight.sh` – validation and ExecStartPre gating (with `--gate-only`)
- `canonical_system_startup.sh` – verifies env + data mount + database, then runs a full reset/start with health summary
- `wait_for_mcp.sh` – helper used by unit template to gate on the MCP bus
- `justnews-start-agent.sh` – unit ExecStart wrapper

Helpers (optional, recommended):
- `helpers/orchestrator-ready.sh` – poll /ready on 8014 with backoff
- `helpers/tail-logs.sh` – follow multiple `journalctl` streams with labels
- `helpers/diag-dump.sh` – capture statuses, logs, ports into a bundle
- `helpers/db-check.sh` – quick DB reachability check
- `run_crawl_schedule.sh` – Stage B1 hourly crawl scheduler entry point (copy to `/usr/local/bin/` and ensure executable)

### Crawl scheduler service (Stage B1)

- Unit: `units/justnews-crawl-scheduler.service` (oneshot wrapper around `run_crawl_schedule.sh`)
- Timer: `units/justnews-crawl-scheduler.timer` (hourly with a 5-minute jitter window)
- Enable sequence:
	1. `sudo cp infrastructure/systemd/scripts/run_crawl_schedule.sh /usr/local/bin/run_crawl_schedule.sh`
	2. `sudo chmod +x /usr/local/bin/run_crawl_schedule.sh`
	3. `sudo cp infrastructure/systemd/units/justnews-crawl-scheduler.* /etc/systemd/system/`
	4. `sudo systemctl daemon-reload`
	5. `sudo systemctl enable --now justnews-crawl-scheduler.timer`
- Optional overrides: `/etc/justnews/crawl_scheduler.env`
	- `CRAWLER_AGENT_URL=http://127.0.0.1:8015`
	- `CRAWL_SCHEDULE_PATH=/etc/justnews/crawl_schedule.yaml` (if relocating config)
	- `CRAWL_PROFILE_PATH=/etc/justnews/crawl_profiles.yaml` (optional path to the Crawl4AI profile registry)
	- `CRAWL_SCHEDULER_METRICS=/var/lib/node_exporter/textfile_collector/crawl_scheduler.prom`
	- `CRAWL_SCHEDULER_STATE=/var/log/justnews/crawl_scheduler_state.json`
	- `CRAWL_SCHEDULER_SUCCESS=/var/log/justnews/crawl_scheduler_success.json`

## Unit template and drop-ins

- Template: `units/justnews@.service` → create instances like `justnews@scout`
- Drop-in templates: `units/drop-ins/` (copy into `/etc/systemd/system/justnews@<name>.service.d/`)
	- `05-gate-timeout.conf` – tune model gate timeout
	- `10-preflight-gating.conf` – run preflight in `--gate-only` mode
	- `20-restart-policy.conf` – restart policy knobs

## Minimal environment files (examples)

Global: `/etc/justnews/global.env`

```
# absolute python for agents
JUSTNEWS_PYTHON=/home/adra/miniconda3/envs/justnews-v2-py312/bin/python

# optional: default working directory
SERVICE_DIR=/home/adra/JustNewsAgent-Clean

# database URL for Memory agent (adjust as needed)
JUSTNEWS_DB_URL=postgresql://user:pass@localhost:5432/justnews
```

Per-instance: `/etc/justnews/analyst.env`

```
CUDA_VISIBLE_DEVICES=0
# override exec if needed
# EXEC_START="$JUSTNEWS_PYTHON -m agents.analyst.main"
```

See Quick Reference for the full port map and more examples.

