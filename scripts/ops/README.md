# GPU Incident Collection Script

This script bundles GPU diagnostic outputs into an archive for postmortem analysis.

Usage:

```bash
# default output dir
./scripts/ops/collect_gpu_incident.sh

# specify output dir
./scripts/ops/collect_gpu_incident.sh /tmp/incident-20251210-123456
```

Artifacts collected:
- NVML watchdog logs (/tmp/justnews_perf/nvml_watchdog.jsonl)
- GPU event logs (logs/gpu_events.jsonl)
- `nvidia-smi -q -x` full XML snapshot
- dmesg tail and system logs
- justnews journal logs for justnews services
- coredumpctl listing and environment variables

It is recommended to run this script when investigating driver resets, OOM conditions, or other GPU-related incidents.

--

## Ops Script Helpers

This file also documents a couple of ops helper scripts added recently:

- `integration_smoke_test.sh` — Run a minimal start→smoke→stop harness for a small manifest using a conda shim (safe to run in CI).
- `replace_ports_in_docs.sh` — Scan and optionally replace hard-coded port references in selected docs/configs with placeholders such as `${GRAFANA_PORT}`, `${MCP_BUS_URL}`, and so on.

Run the integration harness:

```bash
bash scripts/ops/integration_smoke_test.sh
```

Check for stale docs ports (dry-run):

```bash
bash scripts/ops/replace_ports_in_docs.sh
```

Apply replacements after reviewing backups (creates `.bak` files):

```bash
bash scripts/ops/replace_ports_in_docs.sh --apply
```

