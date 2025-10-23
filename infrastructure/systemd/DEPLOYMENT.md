---
title: Systemd Deployment Overview
description: Canonical entry-point for deploying and restarting JustNews with systemd
---

# Systemd Deployment – Quick Start

## TL;DR: One-command fresh restart (recommended)

```
sudo ./deploy/systemd/reset_and_start.sh
```

What it does:
- Stops/disables all services, frees ports, reloads systemd if needed
- Ensures GPU Orchestrator is READY before any agents start
- Starts MCP Bus, then all agents in order, then runs health check

## Manual sequence (orchestrator-first)

```
sudo systemctl enable --now justnews@gpu_orchestrator
curl -fsS http://127.0.0.1:8014/ready
sudo ./deploy/systemd/enable_all.sh start
sudo ./deploy/systemd/health_check.sh
```

Notes:
- `enable_all.sh` supports `fresh` and `--fresh` alias and now starts `gpu_orchestrator` first, waiting for `/ready`.
- Adjust gating timeout via drop-in: `Environment=GATE_TIMEOUT=300`.

## Related documentation
- Quick Reference: `deploy/systemd/QUICK_REFERENCE.md`
- Comprehensive Guide: `deploy/systemd/COMPREHENSIVE_SYSTEMD_GUIDE.md`
- PostgreSQL Integration: `deploy/systemd/postgresql_integration.md`

