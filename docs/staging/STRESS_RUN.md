# Running a controlled full-stack stress run (isolated host)

This guide explains how to run a reproducible stress test on an isolated, dedicated staging host (or container) that mirrors your production hardware.

Important safety notes
- Only run this on a dedicated host or isolated container with monitoring and artifact collection enabled. Do NOT run on your local VS Code / laptop where crashes will cause disruption.
- Ensure you have sufficient quotas / monitoring and a plan to stop the test early if things go wrong.
- Run inside the canonical Conda environment (recommended): ${CANONICAL_ENV:-justnews-py312}.

Quick steps
1. Provision an isolated host (GPU + memory similar to production) and clone the repo.
2. Activate canonical env and install dependencies (conda environment.yml or system packages for Playwright browsers).
3. Run the stress harness and monitor CPU/GPU/memory:

```bash
conda activate ${CANONICAL_ENV:-justnews-py312}
# Recommended: run inside a container or VM
# To run a 20-minute stress with 4 concurrent canaries and 2 crawling threads
./scripts/dev/stress_full_e2e.sh 1200 4 2
# This writes logs/artifacts to output/stress_run/
```

Interpret results
- Check `output/stress_run/resource_trace.jsonl` — time-series CPU/RAM/GPU and top processes
- Check `output/stress_run/*.log` for process stdout/stderr
- Use `ps_top.txt` and `nvidia_smi_end.txt` to inspect final process state and GPU consumption

If you reproduce a saturation/crash:
1. Run the stress harness again with higher tracing or smaller concurrency variations to isolate the scenario.
2. Capture core dumps (if enabled) and process logs.
3. Share `output/stress_run` with the dev team for root cause analysis.

Next steps
- After reproducing, we can implement tighter resource constraints, model caching improvements, or fix leaking browser/process handles identified by the trace.
- Optionally, promote the stress run to a CI job on a dedicated self-hosted GPU runner that keeps the artifacts.
