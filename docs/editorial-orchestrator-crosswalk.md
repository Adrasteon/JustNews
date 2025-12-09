## Editorial harness ↔ GPU Orchestrator crosswalk

This short crosswalk documents where the editorial / agent harness (editorial_harness_runner) and the GPU Orchestrator interact, and where teams should look to understand end-to-end flows that require orchestrated GPU resources.

Why this doc exists
- The `live-run-plan.md` covers the end-to-end Crawl → Ingest → Parse → Editorial → Publish flow but doesn't specify orchestration details for GPU-bound operations.
- `workflow_management.md` covers the GPU Orchestrator and job lifecycle, but does not explicitly show where editorial harness and agents call into the orchestrator.

Quick mapping (files & responsibilities)
- Editorial harness and agent chain
  - Primary runner: `agents/common/editorial_harness_runner.py` — orchestrates agent chain, acceptance checks and optional publishing.
  - Runner entrypoint script: `scripts/dev/run_agent_chain_harness.py` (supports `--publish-on-accept --publish-token`).

- Publishing integration
  - Publishing helper: `agents/common/publisher_integration.py` — used by the editorial harness to POST into the lightweight publisher (or call an external publisher endpoint).
  - Publisher app: `agents/publisher/` — receives published article payloads and exposes Prometheus metrics and `/api/metrics/` for CI checks.

- GPU orchestrator / lease & job model
  - Orchestrator service and API: `agents/gpu_orchestrator/main.py` + engine `agents/gpu_orchestrator/gpu_orchestrator_engine.py`.
  - Client helper used by agents: `agents/common/gpu_orchestrator_client.py` — callers can request policies or leases before running GPU workloads.
  - Worker & consumers: `agents/gpu_orchestrator/worker.py`, `job_consumer.py` — Redis Streams consumer patterns and job claim/release semantics.

How the editorial/agent flows tie into the orchestrator
1. Agents that perform GPU-bound tasks should consult `GPUOrchestratorClient` (or post jobs to orchestrator endpoints) before starting work. This enforces safe admission control and prevents GPU storms.
2. For long-running or scheduled workloads the orchestrator accepts job submissions via `POST /jobs/submit` and stores rows in `orchestrator_jobs` and writes to Redis streams like `stream:orchestrator:inference_jobs`.
3. Worker consumers claim jobs, acquire leases and execute. Results and status transitions are persisted in DB (e.g., `orchestrator_jobs` status → `claimed`, `running`, `done`, `failed`, `dead_letter`).

When to call the orchestrator from editorial flows
- Short inference calls (low latency) — prefer in-process model clients or cached embedder pools where appropriate, but consult the orchestrator policy endpoint (`/policy`) if GPU allocation should be gated.
- Long-running or multi-step GPU work (e.g., model fine-tuning, large model inference) — submit to orchestrator via `POST /jobs/submit` so the orchestrator can manage queues, rate-limit, and allocate leases.

Relevant Prometheus metrics & dashboards
- Orchestrator metrics: `gpu_orchestrator_job_queue_depth`, `gpu_orchestrator_leases_active`, `gpu_orchestrator_worker_pools_total` (see `workflow_management.md` and `monitoring/alerts/gpu_orchestrator_*` for rules).
- Editorial harness metrics: `justnews_stage_b_editorial_harness_total` and acceptance metrics — dashboard configured in `docs/grafana/editorial-harness-dashboard.json`.
- Ingestion/raw_html metrics (ingest success/failure/latency) — dashboard added at `docs/grafana/ingest-archive-dashboard.json` to complete E2E observability.

Operational checklist when running editorial jobs requiring GPUs
1. Ensure `GPU_ORCHESTRATOR_URL` and orchestration policy clients are configured in the environment for the agent process.
2. If using `GPUOrchestratorClient`, prefer the policy endpoint for quick checks and `POST /jobs/submit` for large jobs.
3. Make sure leases and worker pools are provisioned and healthy (`GET /workers`, `GET /leases`) before scheduling high concurrency runs.

See also
- `docs/live-run-plan.md` — E2E plan for Crawl → Publish flow.
- `docs/workflow_management.md` — detailed design and runbook for persistent orchestrator, Redis Streams, and jobs.
