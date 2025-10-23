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
	 - `sudo ./deploy/systemd/enable_all.sh start`

3) Check health:
	 - `sudo ./deploy/systemd/health_check.sh`

Troubleshooting? See the Quick Reference and Comprehensive guide below.

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
- `wait_for_mcp.sh` – helper used by unit template to gate on the MCP bus
- `justnews-start-agent.sh` – unit ExecStart wrapper

Helpers (optional, recommended):
- `helpers/orchestrator-ready.sh` – poll /ready on 8014 with backoff
- `helpers/tail-logs.sh` – follow multiple `journalctl` streams with labels
- `helpers/diag-dump.sh` – capture statuses, logs, ports into a bundle
- `helpers/db-check.sh` – quick DB reachability check

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
SERVICE_DIR=/home/adra/justnewsagent/JustNewsAgent

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

