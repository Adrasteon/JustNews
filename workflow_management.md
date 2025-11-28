# Workflow Management — Persistent Orchestration & Resource Control

This document specifies a resilient, persistent orchestration and resource-management plan for JustNews. It captures the design decisions, DB schemas, APIs, message bus (Redis Streams) topics & consumer patterns, safety properties, monitoring, autoscaling, and an incremental implementation plan.

The goal: make the orchestration system durable and leader-aware, prevent GPU/host resource storms, provide dynamic throttles, and ensure work completes without losing state due to crashes or restarts.

---

## Overview — goals

- Persistence: ensure authoritative state (leases, pools, jobs) survives orchestrator crashes and process restarts.
- Monitoring & Observability: real-time telemetry, traces, alerts and dashboards for queue lengths, GPU utilization and worker lifecycle.
- Admission Control & Backpressure: per-agent and global control that can dynamically reduce or increase agent load.
- HA & Recovery: support leader election and reconciliation loops so orchestrator instances can recover state and continue processing.
- Safe scaling: expose metrics to autoscalers (KEDA/HPA) and let the system autoscale worker processes based on meaningful signals.

---

## Components & responsibilities

- MariaDB — persistent authoritative store for leases, worker pools, jobs, and metadata/audit logs.
- Redis Streams — primary job/event bus for durable, reliable messaging with consumer groups and DLQ.
- GPU Orchestrator (agent) — orchestrates leases, worker pools, preloads; leader responsible for reconciliation and admission control.
- Workers (pool processes) — stateless consumers that claim jobs from streams and claim leases before GPU-bound work.
- Metrics & Tracing — Prometheus metrics and OTLP/OTEL traces to provide real-time insights.
- Admission controller — runtime policy module that decides whether to accept or throttle incoming work.

---

## Persistent schema (SQL examples)

Note: these are example schemas for MariaDB. They are intentionally minimal — add indices, constraints, and migrations in real deploys.

DDL (example):

```sql
CREATE TABLE orchestrator_leases (
  token VARCHAR(64) PRIMARY KEY,
  agent_name VARCHAR(255) NOT NULL,
  gpu_index INT NULL,
  mode ENUM('gpu','cpu') NOT NULL DEFAULT 'gpu',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NULL,
  last_heartbeat TIMESTAMP NULL,
  metadata JSON NULL
);

CREATE INDEX idx_leases_agent ON orchestrator_leases(agent_name);

CREATE TABLE worker_pools (
  pool_id VARCHAR(128) PRIMARY KEY,
  agent_name VARCHAR(255) NULL,
  model_id VARCHAR(255) NULL,
  adapter VARCHAR(255) NULL,
  desired_workers INT NOT NULL DEFAULT 0,
  spawned_workers INT NOT NULL DEFAULT 0,
  started_at TIMESTAMP NULL,
  last_heartbeat TIMESTAMP NULL,
  status ENUM('starting','running','draining','stopped','evicted') NOT NULL DEFAULT 'starting',
  hold_seconds INT NOT NULL DEFAULT 600,
  metadata JSON NULL
);

CREATE TABLE orchestrator_jobs (
  job_id VARCHAR(128) PRIMARY KEY,
  type VARCHAR(64) NOT NULL,
  payload JSON NOT NULL,
  status ENUM('pending','claimed','running','done','failed','dead_letter') NOT NULL DEFAULT 'pending',
  owner_pool VARCHAR(128) NULL,
  attempts INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NULL,
  last_error TEXT NULL
);

CREATE TABLE orchestrator_audit (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  event_type VARCHAR(128),
  details JSON
);
```

Guideline: always persist a `job_id` (client-supplied or generated) so handlers are idempotent.

---

## Redis Streams topics & consumer patterns

Why Redis Streams: small ops footprint, consumer groups, exactly-once-ish semantics with XCLAIM/ACK and IDLE detection, and easy horizontal scaling.

Recommended streams:

- stream:orchestrator:preloads — used for model preload / warm pool start requests
- stream:orchestrator:inference_jobs — heavy (GPU) tasks that must obtain a lease before running
- stream:orchestrator:ingest_events — events like memory.ingest_article → archive triggers, downstream tasks
- stream:orchestrator:control — control & admin events (evict pool, force-stop, drain)

Consumer group naming:
- cg:preloads:workers (orchestrator and worker processes can have distinct consumer groups)
- cg:inference:pool-X (pool-specific consumer groups for isolated pools)

Consumer model:
- Producers push into stream with a job payload and a stable job_id.
- A consumer group consumer claims a message via XREADGROUP; on start it marks job status=claimed and records worker+lease (DB update).
- On success finalizes job as `done` and ACKs the stream; on failure increments `attempts` and optionally XACK+XADD to DLQ.
- If consumer dies with an unacked message, the leader or a reclaimer process will XCLAIM messages where IDLE time > threshold and handle retries.

Dead-letter & retries:
- Use stream:orchestrator:dlq with job header fields: job_id, origin_id, attempts, last_error.
- Implement exponential backoff queueing by requeuing with computed delay fields or auxiliary delayed queues.

---

## API contract — persistent orchestrator endpoints (examples)

We adapt the existing orchestrator endpoints to use persistent storage and leader semantics.

1) Leases

GET /leases — list leases (admin/read-only)
POST /leases — request lease
  body: { "agent": "embedder", "min_memory_mb": 2000, "ttl_seconds": 3600 }
  returns: { "granted": true, "token": "uuid", "gpu_index": 0, "expires_at": "ts" }

POST /leases/{token}/heartbeat — body: { "timestamp": "ts" }  -> updates last_heartbeat. Not optional.

POST /leases/{token}/release — returns release confirmation. On release orchestrator will also update DB and audit log.

2) Worker pools
 This document specifies a resilient, persistent orchestration and resource-management plan for JustNews. It captures the design decisions, DB schemas, APIs, message bus (Redis Streams) topics & consumer patterns, safety properties, monitoring, autoscaling, and a detailed, incremental implementation and operational guide. It is maintained alongside the implementation in agents/gpu_orchestrator and the repo's integration tests.
   "variant": "fp16"
 
 NOTE — status summary (as of latest changes):
 - Core persistent features implemented and covered by tests: persisted leases (orchestrator_leases), persisted worker pools (worker_pools), persistent jobs (orchestrator_jobs), a reclaimer for unacked messages, and leader election / HA control. Worker process lifecycle, job claiming, lease acquisition/release, DLQ handling, and reclaimer logic are implemented in agents/gpu_orchestrator and are exercised by unit and integration tests under tests/unit and tests/integration.
 - MariaDB — persistent authoritative store for leases, worker pools, jobs, and metadata/audit logs. Schemas added in scripts/init_database.py and scripts/deploy/init_database.py. Tests exercise a conformed sqlite test harness that maps MySQL-style placeholders to sqlite for CI-friendly runs.
POST /jobs/submit — body includes stable job_id, type, payload. Orchestrator persists job row and pushes into Redis stream for consumers.
 Consumer model (implemented)
 This behavior has been implemented and tested in the engine's reclaimer and worker implementation. Important implementation notes:
 
 - The Worker (agents/gpu_orchestrator/worker.py) uses a best-effort fallback (xrange) where xreadgroup is not present, decodes fields, normalizes job ids and payloads, updates orchestrator_jobs status transitions (claimed -> done/failed), and ACKs messages.
 - The engine's `_reclaimer_pass` examines pending entries older than ORCH_CLAIM_IDLE_MS, increments attempts, requeues or moves messages to DLQ, and updates `orchestrator_jobs` accordingly. Unit tests cover both requeue and DLQ behavior.
4) Health & leader
 POST /leases/{token}/heartbeat — body: { "timestamp": "ts" }  -> updates last_heartbeat. Not optional. (Implemented in main endpoints & engine heartbeat_lease.)
 POST /jobs/submit — body includes stable job_id, type, payload. Orchestrator persists job row and pushes into Redis stream for consumers. (Implemented: engine.submit_job persists job and writes to Redis stream when a Redis client is available.)
 POST /control/reconcile — request immediate reconciliation (only leader will act)
 
 NOTE: Many of the above endpoints are available in agents/gpu_orchestrator/main.py for local testing. See that module for the FastAPI routes and how the engine integrates with the web layer.
 This is implemented using MariaDB GET_LOCK-based leader election and a background reconciliation/reclaimer loop in the engine. Only the leader performs lifecycle enforcement and reclaimer passes. Leader takeover is guarded by acquiring the DB advisory lock and the engine logs leader transitions.
POST /control/evict_pool — admin API to evict
 ### Phase 6 — Worker + lease usage and job lifecycle (IMPLEMENTED)
 - Worker implementation completed. `agents/gpu_orchestrator/worker.py` implements a simple worker that claims messages, requests leases from the engine, updates orchestrator_jobs status transitions and releases leases.
 - Integration tests added: tests/integration/test_worker_flow.py verifies worker end-to-end behavior (claimed -> done, failure handling, lease denial behavior).
 
 ### Phase 7 — Next & operational tasks
 - Add more robust claim,XCLAIM/XAUTOCLAIM semantics for production Redis, improve idempotency guarantees and timeouts on job execution.
 - Add more monitoring & autoscaler rules based on historical metrics.
 - **TODO**: Revisit E2E testing strategy. The systemd-nspawn approach proved too complex/fragile (disabled for now). Consider Docker-based E2E tests or cloud-based test environments for real Redis/MariaDB testing — note: the Docker Compose PoC is provided for lightweight local testing and CI only; the primary/preferred MariaDB deployment runs on the host or as a managed DB instance outside Docker. See docs/dev/systemd-nspawn.md for context on why it was disabled.
 - **TODO**: Revisit E2E testing strategy. The systemd-nspawn approach proved too complex/fragile (disabled for now). We added a Docker-based E2E proof-of-concept for lightweight testing and CI only — see `scripts/dev/docker-compose.e2e.yml` and `scripts/dev/run_e2e_docker.sh` for a local PoC and `.github/workflows/e2e-docker.yml` for a manual CI job. Reminder: in normal developer and production workflows the canonical MariaDB deployment runs on the host (outside Docker) or as a managed service.

---

## Leader election & reconciliation

Leader election options:
- MariaDB advisory lock (e.g., GET_LOCK('gpu_orchestrator_leader', <timeout>)) — simple, uses DB.
- Or Redis LOCK with TTL & renewals (Redlock variant) — fast and works cross-process.

Simple pattern: try to acquire lock on startup; if success become leader and start reconciliation loops, spawn enforcer threads. Renew lock periodically; if fails, relinquish leader role and stop controlling operations.

Reconciliation loop responsibilities (leader only):
- Compare DB worker_pools state to in-memory _WORKER_POOLS and spawn/evict processes as required.
- Purge expired leases and mark them in DB.
- Reclaimer: find XGROUP pending/idle messages and reassign after XCLAIM threshold.
- Maintain metrics (worker counts, pool evictions, lease counts) via Prometheus.

---

## Admission control & safety rules

- Token-bucket per-agent limit persisted in DB / policy: rate + burst capacity.
- Global admission gates:
  - If global GPU memory usage > 90% -> stop accepting new GPU inference jobs for X seconds
  - If queue depth grows above threshold -> trigger scale-up, or reject/route to CPU fallback
  - Configurable per-agent low/high watermarks for memory & tasks

- Pool draining procedure (safe stop):
  - set pool.status='draining'
  - stop accepting new jobs for that pool
  - wait for running jobs to complete (with graceful timeout)
  - release leases and mark pool.status='stopped'

---

## Autoscaling & metrics

Expose the following Prometheus metrics (examples):
- gpu_orchestrator_leases_active
- gpu_orchestrator_leases_free
- gpu_orchestrator_worker_pools_total
- gpu_orchestrator_worker_pool_workers{pool_id}
- gpu_orchestrator_job_queue_depth{stream}
- gpu_orchestrator_gpu_mem_used_pct{gpu_index}
- gpu_orchestrator_job_latency_seconds{type}

Use these metrics as inputs to KEDA scalers or HPA.

Example autoscaling policy: scale workers when queue depth > 100 OR mean job latency > 2s; scale down when queue depth is low and utilization is < 10%.

---

## Safety and correctness

- All major state transitions are persisted in DB with audit rows.
- Job handlers should be idempotent; they must check job_id against DB job status before performing work.
- Use DB transactions when acquiring a lease + claiming a job to avoid races.
- Use heartbeats with TTL: if heartbeat stops beyond threshold, orchestrator marks worker as dead and reclaims jobs and leases.
- Dead letter queue and retry policy with jitter and exponential backoff for transient failures.

---

## Incremental implementation plan

We will implement in small, verified steps so the live system remains stable.

### Phase 1 — Durable leases (PoC)
- Add `orchestrator_leases` table and API heartbeat endpoints.
- Make `GPUOrchestratorEngine.lease_gpu` create persisted rows and return token & expires_at.
- Add `lease_heartbeat` endpoint and a background purge job that reclaims expired leases.
- Tests:
  - unit tests for DB helpers
  - integration-style test where we create lease, kill orchestrator (simulate restart), start new orchestrator, and verify lease still present and TTL enforced

Deliverable: leases are persisted, survive restarts, and can be reclaimed.

### Phase 2 — Durable worker pools
- Add `worker_pools` database table and persistent lifecycle management.
- When `POST /workers/pool` is called store row and emit a stream event.
- Add workerheartbeat endpoint so pools/workers heartbeat and update `spawned_workers`.
- Add reconciliation loop that rehydrates and enforces pools on leader startup.
- Tests: verify pool survival across orchestrator restarts; pool draining tests.

### Phase 3 — Job queue (Redis Streams)
- Add `orchestrator_jobs` table and `stream:orchestrator:inference_jobs`, `stream:orchestrator:preloads`.
- `POST /jobs/submit` persists job and writes into redis stream.
- Implement a consumer skeleton that claims jobs, persists `claimed` status, requests lease, runs job, finalizes status and ACKs.
- Implement DLQ & requeue logic.
- Tests: end-to-end job submit/claim/success/failure, reclaimer handling unacked messages.

### Phase 4 — Leader election & HA
- Implement leader lock (DB advisory lock or Redis lock), and ensure leader-only duties are gated by lock.
- Add graceful takeover on leader failure.
- Tests: simulate leader crash and verify another orchestrator becomes leader and resumes reconciliation.

### Phase 5 — Monitoring & Autoscale
- Add metrics for queue depth, job latency, GPU utilization etc.
- Add Grafana dashboard and KEDA/HPA scaler rules.
- Tests: smoke tests that instrument metrics and verify autoscaler inputs exist.

### Phase 6 — Admission control & anti-storm policies
- Implement per-agent token buckets and global admission rules.
- Add policy runtime config APIs.
- Tests: simulate flood of submissions and verify throttling and fallback to CPU implementations.

### Phase 7 — E2E integration & operator runbook
- Add integrated tests for crash-restart resilience, DLQ, graceful drain, and backpressure behavior.
- Create an operator runbook: how to force-evict pools, drain cluster, recover from dead leader, and emergency steps for OOM.

---

## Example small flows

1) Agent requests GPU work:
  - Agent calls POST /jobs/submit with job_id
  - Orchestrator persists job row, pushes to stream:orchestrator:inference_jobs
  - Consumer picks job, sets status=claimed, requests a lease in transactional manner
  - If lease granted, consumer executes and updates status=running
  - On completion, update status=done and ACK stream record

2) Pool creation (mistral warm pool)
  - UI or script calls POST /workers/pool
  - Orchestrator persists worker_pools row and writes stream:orchestrator:preloads
  - A PoolProvisioner consumer takes the message, provisions pool workers (spawned by orchestrator or external worker supervisor), persists spawned count and heartbeats
  - Pool lasts until hold_seconds expire, or admin drains or pool.status sets to 'draining'

---

## Example checks & operator commands

- Reconcile immediately (admin): POST /control/reconcile
- Force-stop a pool: POST /control/evict_pool {pool_id}
- List active leases: GET /leases

---

## Notes & migration guidance

- Start with PoC (persistent leases) and add telemetry & tests. Avoid big-bang replacements in production.
- Ensure the DB migration path is tested and the orchestrator can work in hybrid mode (DB-backed leases optional) while rolling out migration.
- Keep short TTLs for locks/heartbeats initially during testing to allow fast failover iterations.

---

## Next steps

- Implementation: build DB migrations and persistent adapters for `GPUOrchestratorEngine`.
- Tests: add unit + integration tests to the repo (using the existing conftest test harness and a test DB).
- Ops: add Redis to local dev infra for streams; add a Grafana dashboard & KEDA rules; add runbooks.

---

## Appendix — sample Redis stream usage (commands)

Producer push example:
```
XADD stream:orchestrator:inference_jobs * job_id "123" type "inference" payload '{...}'
```

Create consumer group:
```
XGROUP CREATE stream:orchestrator:inference_jobs cg:inference $ MKSTREAM
```

Consume (XREADGROUP):
```
XREADGROUP GROUP cg:inference consumer-1 COUNT 1 BLOCK 2000 STREAMS stream:orchestrator:inference_jobs >
```

Claim stale message (reclaimer):
```
XCLAIM stream:orchestrator:inference_jobs cg:inference consumer-2 0-0-0-0 IDLE 60000 XX
```

ACK when done:
```
XACK stream:orchestrator:inference_jobs cg:inference <id>
```

---

End of doc.
