---
title: Systemd Quick Reference
description: 'This enables units (if needed), ensures GPU orchestrator is READY, starts all services in order, and verifies health.'

tags: ["enables", "ensures", "health"]
---

# Quick Reference – systemd

## One-command cold start (after reboot)

```
sudo ./deploy/systemd/cold_start.sh
```

This enables units (if needed), ensures GPU orchestrator is READY, starts all services in order, and verifies health.

Optional: Auto-run at boot (~45s):

```
sudo cp deploy/systemd/scripts/justnews-cold-start.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/justnews-cold-start.sh
sudo cp deploy/systemd/units/justnews-cold-start.service /etc/systemd/system/
sudo cp deploy/systemd/units/justnews-cold-start.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now justnews-cold-start.timer
```

Optional: Boot-time smoke test (~2 min after boot):

```
sudo cp deploy/systemd/helpers/boot_smoke_test.sh /usr/local/bin/
sudo cp deploy/systemd/scripts/justnews-boot-smoke.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/justnews-boot-smoke.sh /usr/local/bin/boot_smoke_test.sh
sudo cp deploy/systemd/units/justnews-boot-smoke.service /etc/systemd/system/
sudo cp deploy/systemd/units/justnews-boot-smoke.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now justnews-boot-smoke.timer
```

## One-command fresh restart (recommended)

```
sudo ./deploy/systemd/reset_and_start.sh
```

This performs a clean stop, frees ports, ensures the GPU orchestrator is READY, starts all services in order, and runs a health check.

## Startup order (orchestrator-first)

1) Start GPU Orchestrator (models gate):

```
sudo systemctl enable --now justnews@gpu_orchestrator
curl -fsS http://127.0.0.1:8014/ready
```

2) Start all services in order:

```
sudo ./deploy/systemd/enable_all.sh start
```

3) Check health:

```
sudo ./deploy/systemd/health_check.sh
```

Tip: `enable_all.sh` defaults to `status` with no args. Use `start`, `stop`, `restart`, or `fresh` (also accepts `--fresh`).

## Ports and health endpoints

| Service           | Port | Endpoint |
|-------------------|------|----------|
| mcp_bus           | 8000 | /health  |
| chief_editor      | 8001 | /health  |
| scout             | 8002 | /health  |
| fact_checker      | 8003 | /health  |
| analyst           | 8004 | /health  |
| synthesizer       | 8005 | /health  |
| critic            | 8006 | /health  |
| memory            | 8007 | /health  |
| reasoning         | 8008 | /health  |
| newsreader        | 8009 | /health  |
| balancer          | 8010 | /health  |
| analytics         | 8011 | /health  |
| archive           | 8012 | /health  |
| dashboard         | 8013 | /health  |
| gpu_orchestrator  | 8014 | /health, /ready, /models/status |

Examples:

```
curl -fsS http://127.0.0.1:8004/health    # analyst
curl -fsS http://127.0.0.1:8014/ready     # orchestrator ready
curl -fsS http://127.0.0.1:8014/models/status | jq
```

## Minimal environment files

Global (`/etc/justnews/global.env`):

```
JUSTNEWS_PYTHON=/home/adra/miniconda3/envs/justnews-v2-py312/bin/python
SERVICE_DIR=/home/adra/justnewsagent/JustNewsAgent
JUSTNEWS_DB_URL=postgresql://user:pass@localhost:5432/justnews
ENABLE_MPS=true
```

Per-instance (example `/etc/justnews/analyst.env`):

```
CUDA_VISIBLE_DEVICES=0
```

## NVIDIA MPS Setup (Enterprise GPU Isolation)

Enable NVIDIA Multi-Process Service for GPU resource isolation:

1. **Start MPS Daemon** (run once at system boot):
```bash
sudo nvidia-cuda-mps-control -d
```

2. **Verify MPS Status**:
```bash
pgrep -x nvidia-cuda-mps-control
ls -la /tmp/nvidia-mps/
```

3. **Environment Configuration**:
   - Set `ENABLE_MPS=true` in `/etc/justnews/global.env`
   - Set `ENABLE_MPS=true` and `ENABLE_NVML=true` in `/etc/justnews/gpu_orchestrator.env`

4. **Check MPS Allocation**:
```bash
curl -s http://127.0.0.1:8014/mps/allocation | jq '.mps_resource_allocation.system_summary'
```

## Common operations

```
sudo systemctl status justnews@scout
sudo journalctl -u justnews@scout -e -n 200 -f
sudo ./deploy/systemd/enable_all.sh status
sudo ./deploy/systemd/enable_all.sh restart
```

## Orderly shutdown (all agents)

```
sudo ./deploy/systemd/enable_all.sh stop
```

Notes:
- Stops all JustNews instances in reverse dependency order.
- Does not stop PostgreSQL (managed separately by your OS/service).
- To also stop the orchestrator explicitly:

```
sudo systemctl stop justnews@gpu_orchestrator
```

Troubleshooting:
- If ports remain in use, run: `sudo ./deploy/systemd/preflight.sh --stop`.
- Inspect logs: `journalctl -u justnews@<name> -e -n 200`.

## Optional: PATH wrappers (run from any directory)

Install small wrappers to `/usr/local/bin` so these commands work regardless of your current directory:

```
sudo cp deploy/systemd/scripts/enable_all.sh /usr/local/bin/
sudo cp deploy/systemd/scripts/health_check.sh /usr/local/bin/
sudo cp deploy/systemd/scripts/reset_and_start.sh /usr/local/bin/
sudo cp deploy/systemd/scripts/cold_start.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/enable_all.sh /usr/local/bin/health_check.sh \
	/usr/local/bin/reset_and_start.sh /usr/local/bin/cold_start.sh
```

Then you can run:

```
sudo enable_all.sh stop
sudo reset_and_start.sh
sudo cold_start.sh
sudo health_check.sh
```

These wrappers resolve `JUSTNEWS_ROOT` or `SERVICE_DIR` from `/etc/justnews/global.env` automatically.

## Status panel (auto-refresh health)

Open a live, auto-refreshing system health panel:

```
sudo health_check.sh --panel
```

Options:
- `--refresh SEC` to change interval (default: 2)
- `--host HOST` and `-t/--timeout SEC` respected
- Limit to specific services, e.g.: `sudo health_check.sh --panel mcp_bus analyst`

Notes:
- Tries to launch a new terminal (x-terminal-emulator/gnome-terminal/konsole/xterm).
- Falls back to tmux (new window) if available; otherwise runs inline via `watch`.
- Ensure `watch` (procps) is installed on servers.

## Troubleshooting first-run issues

- Many services “failed/inactive” immediately:
	- Ensure orchestrator is running and READY (see startup order above).
- Preflight shows “run as root” and exit 1 under systemd:
	- Expected for ExecStartPre limited checks; continue with orchestrator-first.
- Ports already in use:
	- `sudo ./deploy/systemd/preflight.sh --stop` to free conflicting services.
- DB connectivity (Memory):
	- Set `JUSTNEWS_DB_URL` in `global.env` and run `helpers/db-check.sh`.

## Install helpers (optional)

```
sudo cp deploy/systemd/wait_for_mcp.sh /usr/local/bin/
sudo cp deploy/systemd/justnews-start-agent.sh /usr/local/bin/
sudo cp -r deploy/systemd/helpers/* /usr/local/bin/
sudo chmod +x /usr/local/bin/wait_for_mcp.sh /usr/local/bin/justnews-start-agent.sh /usr/local/bin/*
```

