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
