# Running Order — full live E2E test orchestration (live DB + full models + GPUs)

Purpose
- Provide a reproducible "running order" for a fully live end-to-end test that exercises *real production-like assets* (databases, ModelStore, GPUs, Playwright browsers, Crawl4AI, etc.).
- Ensure durable, timestamped logs and resource snapshots are recorded before and after each stage so every stage's inputs/results/resources are auditable.
- Provide an operator-friendly runner that can be executed on a dedicated staging host or self-hosted CI runner.

Key requirements
- Run stages sequentially (not parallel) so resource usage is measured and logged between stages.
- Capture process-level and GPU metrics before and after each stage and persist them to disk immediately so crash recovery still yields useful forensic artifacts.
- Capture stdout/stderr of each stage to separate log files and ensure they are flushed and present before the next stage starts.
- Use clear, minimal timeouts and exit codes per stage; fail early with artifacts archived when a stage fails.

Stages
1. Crawl (Crawl4AI/Playwright) — full crawl run across a small canary set
2. Normalize — archive -> normalize pipeline that writes to live DB (staging DB)
3. Parse / Extraction — parse content with full model-assisted extraction where applicable
4. Editorial harness — full harness invocation with Mistral / model-backed checks
5. Publish — publisher ingestion and render checks
6. Training (optional) — quick training / ModelStore write check (safe & small)
7. KG ingestion (optional) — attempt KG ingestion / query check

Data & logs produced (persisted per run)
- output/running_order/YYYYMMDD_HHMMSS/metadata.json — structured JSON describing stage start/end timestamps, return codes, log paths and resource snapshots
- output/running_order/YYYYMMDD_HHMMSS/logs/{stage}.stdout.log — stage stdout
- output/running_order/YYYYMMDD_HHMMSS/logs/{stage}.stderr.log — stage stderr
- output/running_order/YYYYMMDD_HHMMSS/resource_trace.jsonl — resource monitor snapshots taken BEFORE and AFTER each stage, and optionally at a sampling interval across long-running stages

Safety & environment
- Run only on an isolated staging host or in a self-hosted runner labelled for stress runs. Do NOT run on your laptop/VS Code host.
- Ensure the canonical conda environment is present and `MODEL_STORE_ROOT`, DB credentials, and other sensitive env vars are set securely on the host.
- The runner respects DRY_RUN env and can be configured to actually load models (live mode) or run in dry-run mode for safer debugging.

How to run
- Provision a dedicated staging host, install the canonical conda environment, ensure Playwright browsers are installed and DB + ModelStore are available.
- On the staging host (recommended):

```bash
conda activate ${CANONICAL_ENV:-justnews-py312}
# Run a full live order (live models + DB + GPUs)
PYTHONPATH=$(pwd) python scripts/dev/run_full_live_order.py --output output/running_order --live 1

Example: run the full live order and enable optional training + KG stages:

```bash
PYTHONPATH=$(pwd) python scripts/dev/run_full_live_order.py --output output/running_order --live 1 --enable-training --enable-kg
```

# For a safer, diagnostic run (models disabled):
PYTHONPATH=$(pwd) MODEL_STORE_DRY_RUN=1 python scripts/dev/run_full_live_order.py --output output/running_order --live 0
```

Operator guidance
- The script will produce artifacts under `output/running_order/<timestamp>/` — collect those artifacts for post-mortem if the run fails or if you want to tune resource thresholds.
- The JSON `metadata.json` contains stage-by-stage entries with start/end timestamps, return codes, captured resource summaries (RSS, CPU, GPU usage) and top process lists.
- If a stage fails, the runner stops and writes the metadata; do not immediately re-run without diagnosing the failure logs.

Next steps
- Consider adding a scheduled weekly run on a dedicated self-hosted runner and archive artifacts to object storage for historical analysis.
- Add automated parsers that convert resource_trace.jsonl into graphs for quick triage.
