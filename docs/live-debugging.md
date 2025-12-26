# Live debugging and observability runbook

This runbook explains recommended workflows for running JustNews in "live" mode (full system) while still giving developers safe, effective debugging and real-time observability.

Goals

- Start and supervise the full system without risking unstable desktop GPU usage.

- Capture logs & traces centrally for triage (OTel + Loki/Tempo / local aggregator).

- Allow a developer to attach VS Code to a single service for step-through debugging.

Overview

- Use systemd or docker-compose to start background services (MariaDB, Redis, Chroma, MCP Bus, agents).

- Run OpenTelemetry node + central collectors (or use the dev telemetry docker-compose included in the repo) to capture kernel / NVIDIA logs plus application OTLP.

- When debugging a service interactively, attach VS Code to the service using debugpy (see `.vscode/launch.json`). Avoid attaching debuggers to multiple heavy services simultaneously.

Safety & GPU guidance

- Never run a broad full-suite test or the entire production agent set on your development desktop with GPUs enabled. Use `CUDA_VISIBLE_DEVICES` and container device limits to isolate GPU access.

- Prefer dedicated GPU hosts or CI runners when stressing models or running large e2e workloads.

Quick developer recipes

1) Start the whole system (supervised services)

Use the recommended systemd units (if installed) or helper compose scripts in `scripts/dev/` to start the system. Example:

```bash

## start services with systemd (operators)
sudo systemctl start justnews@*

## or, use the project's dev docker compose for local stacks (services only)
docker compose -f scripts/dev/docker-compose.e2e.yml up -d
```

2) Run local telemetry (dev) to capture logs/traces

The repo includes a small compose file to start a local telemetry stack (Loki + Tempo + a node-collector). See `infrastructure/monitoring/dev-docker-compose.yaml`.

```bash
 docker compose -f infrastructure/monitoring/dev-docker-compose.yaml up -d

## Validate OTEL node collector health
curl -s http://localhost:8889/metrics | head -n 10
```

You can verify the dev stack is functioning with the included demo emitter service which sends a trace and a sample log to the collectors and exposes a probe on http://localhost:8080/. A CI workflow `/.github/workflows/telemetry-smoke.yml` is included to exercise this stack on demand.

To use the helper script added to `scripts/dev/dev-telemetry-up.sh` make it executable if needed:

```bash
chmod +x scripts/dev/dev-telemetry-up.sh
./scripts/dev/dev-telemetry-up.sh
```

If you want the telemetry stack to be started automatically by the canonical
system startup tools, set `ENABLE_DEV_TELEMETRY=true` in `/etc/justnews/global.env`.
This will cause `infrastructure/systemd/canonical_system_startup.sh` to bring up
the local telemetry docker-compose during the normal start flow and tear it down
when `canonical_system_startup.sh stop` is invoked. This is strictly opt-in and
safe for operator-managed hosts.

Optional: Sentry (error reporting)
---------------------------------

For low-friction error reporting you can opt-in Sentry by setting `SENTRY_DSN` in
`/etc/justnews/global.env` or as a per-service environment variable. The repo includes
`monitoring/ops/sentry_example.md` with minimal integration patterns and a manual
CI workflow (`.github/workflows/sentry-sandbox.yml`) to validate a sandbox DSN.

Use conservative settings for development: keep `SENTRY_TRACES_SAMPLE_RATE=0.0` and only
capture ERROR-level events unless you explicitly increase sample rate for a targeted test.

3) Attach VS Code to an agent for deep debugging

Open the repo in VS Code, then in the Run panel choose one of the `Attach` configurations (listed in `.vscode/launch.json`). If starting the service manually, use the sample command below to run the service with debugpy listening on port 5678 and waiting for the client:

```bash
conda activate ${CANONICAL_ENV:-justnews-py312}
python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m agents.gpu_orchestrator.main
```

Then attach the VS Code 'Python: Attach to GPU Orchestrator' configuration and set breakpoints.

4) Inspecting logs and traces

- Use the node collector UI and Loki (or `docker logs` / `journalctl -u justnews@<service>`) to tail logs for real-time errors.

- Use Grafana or Tempo UI to view traces and correlate span IDs with logs.

Backups & troubleshooting

- If the collector fails to start, run the `--dry-run` check using the installed `otelcol-contrib` binary and watch `journalctl -u justnews-otel-*.service`.

- If you encounter desktop instability when running heavy workloads, confirm GPU isolation (`nvidia-smi`) and consider limiting GPU access to a dedicated host.

If you'd like, I can also add step-by-step guided scripts to automate the above. Want me to add a `scripts/dev/dev-telemetry-up.sh` helper next?
