Orchestrator integration
------------------------
The `gpu_orchestrator`/GPU manager can optionally trigger host-level telemetry automatically when an allocation is created and stop it when allocations are released. Enable this behavior on orchestrator hosts with the environment variable:
```
export GPU_TELEMETRY_AUTOSTART=true
```

When enabled the GPU allocation path will attempt to start system telemetry (via systemd service or fallback to the local agent script) and stop it when no active allocations remain. This is recommended on dedicated GPU worker nodes so telemetry is always captured during model runtimes.
# GPU Telemetry & Activity Monitoring — integration guide

This document explains how telemetry and the GPU activity monitor integrate with the JustNews GPU orchestration stack.

Goals
- Automatically collect GPU and host telemetry whenever the GPU is under load
- Keep telemetry off during idle periods to reduce noise and IO overhead
- Provide a Prometheus-friendly exporter for dashboards and alerting

Components
- scripts/perf/gpu_telemetry.sh — CSV per-second telemetry collector (nvidia-smi + hwmon)
- scripts/perf/gpu_telemetry_exporter.py — Prometheus exporter exposing the same metrics
- scripts/perf/gpu_activity_agent.py — Agent that automatically starts/stops telemetry + exporter based on GPU activity

How it works
1. The GPU activity agent polls nvidia-smi every second (configurable). When it observes sustained GPU utilization above a configured threshold the agent starts the CSV collector and the Prometheus exporter.
2. When GPU utilization drops and remains below a configured threshold for a configurable period, the agent stops both services.

Deployment modes
- Separate lightweight agent per host (recommended) — run `gpu_activity_agent.py` as a systemd unit or container on gpu hosts.
- Orchestrator-integrated (advanced) — the `gpu_orchestrator` can call (or listen to) the agent's start/stop events to co-ordinate telemetry capture with job allocation.

Recommended systemd service (example)
```
[Unit]
Description=JustNews GPU activity monitor
After=network.target

[Service]
Type=simple
User=justnews
ExecStart=/usr/bin/python3 /home/adra/JustNews/scripts/perf/gpu_activity_agent.py --start-util 20 --start-seconds 5 --stop-util 10 --stop-seconds 15
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Notes & Security
- RAPL energy files (CPU package power) are often root-readable only. There are two safe options:
  - run the telemetry under a service account with appropriate group-read access to `/sys/class/powercap/...` (preferred) or
  - run telemetry under sudo (less recommended).
- Telemetry files are written to `/var/log/justnews-perf` by default; ensure retention/rotation is configured by ops (logrotate) if tests are long-running.

Next steps
- Integrate the agent into your GPU node provisioning (systemd, container) and add a Prometheus scrape job for the exporter port. Optionally, add alerts (high GPU temp, sudden drop in CPU/RAPL readings) to the monitoring stack.

Installation notes
------------------
We've included helper scripts to install the service and logrotate policy into the host system. On a target GPU host run (requires sudo):

```bash
# Install logrotate and the systemd unit + defaults (installs /etc/logrotate.d/justnews-perf and /etc/default/justnews-gpu-telemetry)
sudo scripts/perf/install_all.sh

# Or do the steps individually if you want finer control
sudo scripts/perf/install_logrotate.sh
sudo scripts/perf/install_service.sh
```

The installer writes a runtime configuration file at `/etc/default/justnews-gpu-telemetry` with values the service reads at startup. Edit this file to change the service user, working directory, log directory, exporter port, and the start/stop thresholds.

Example entries you can tune in `/etc/default/justnews-gpu-telemetry`:

```
JN_USER=justnews
JN_GROUP=syslog
JN_WORKDIR=/home/justnews/JustNews
JN_LOGDIR=/var/log/justnews-perf
JN_EXPORTER_PORT=9118
JN_START_UTIL=20
JN_START_SECONDS=5
JN_STOP_UTIL=10
JN_STOP_SECONDS=15
```

After editing `/etc/default/justnews-gpu-telemetry` restart the service to apply changes:

```bash
sudo systemctl restart justnews-gpu-telemetry.service
```
