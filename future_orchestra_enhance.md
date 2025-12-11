# Future Orchestrator Enhancements — Proposal

This document summarizes a recommended, production-grade design and implementation plan for enhancing the JustNews orchestration and agent architecture. It focuses on:
- Decoupling decision-making from execution
- Scalable event-driven orchestration
- Strong resource governance to avoid OOM/runaway processes
- Observability, telemetry, and failure handling

This document is intended to be used as a policy and technical plan for improving the orchestration surface and the 24/7 automation readiness of JustNews.

---

## TL;DR

- Keep the Chief Editor as a decision/policy engine (not a dispatcher). It should publish lightweight editorial decisions into a reliable event bus.
- Use a durable, partitioned event bus for the data plane (Kafka/Redpanda recommended) and keep MCP Bus for the control plane (RPC, registration).
- Implement an `editorial_dispatcher` worker that routes editorial decisions to `job.dispatch` topics based on policy and resource hints.
- Strongly enforce resource limits (RLIMIT, container limits), lease/heartbeat TTLs, and a reclaimer to prevent runaway jobs.
- Add admission control using a resource estimator and leverage autoscaling/controllers to manage load.
- Implement DLQ, robust retries, and a compacted audit topic for replays and debugging.

---

## Goals

1. Scale to continuous crawling and automated agent processing 24/7.
2. Maintain clear separation of responsibilities: Chief Editor for decisions, Dispatcher for routing, Orchestrator for resource allocation and workers for execution.
3. Prevent OOM/runaway tasks and limit operator intervention for automated events.
4. Provide reliable observability, traceability, and safety mechanisms (DLQ, retries, audit logs).

---

## Key Components

- **Decision Layer:** Chief Editor; publishes `editorial.decisions` events.
- **Dispatcher Layer:** `editorial_dispatcher` reads decisions and emits `job.dispatch` events or calls MCP Bus for synchronous paths.
- **Orchestration Layer:** GPU Orchestrator & worker pools; enforces leases, quotas, and worker pools.
- **Workers:** Execute jobs; use RLIMIT/containerization; publish `job.status` events.
- **Event Bus:** Kafka/Redpanda (recommended) or Redis Streams for the data plane.
- **Control Bus:** MCP Bus for synchronous, low-volume RPC.
- **Monitoring:** Prometheus, Grafana, OTEL tracing, NVML watchdog for GPU health.

---

## Event Topics (Canonical)

- `editorial.decisions` — Decisions emitted by Chief Editor.
- `job.dispatch` — Jobs to be executed: type {analysis, inference, synthesis}.
- `job.status` — Job lifecycle updates: queued → claimed → running → done/failed/dlq.
- `ingest.candidates` — Crawler output stream.
- `audit.decisions` — Compacted audit of decisions for traceability.
- `job.dispatch.dlq` — Dead letter queue for failed jobs.

Partitioning: use `article_id` or `job_id` as key to retain per-article ordering while enabling parallel processing.

---

## Resource Governance & Safety Mechanisms

1. **Admission Control**
   - `lease_gpu()` checks GPU availability and host RAM before accepting jobs.
   - `min_memory_mb` and `max_cpu_seconds` metadata are mandatory for jobs that may be heavy.

2. **Process Limits & Sandboxing**
   - Execute job handlers in a subprocess (or container) with `resource.setrlimit()` for `RLIMIT_AS` (address space), `RLIMIT_CPU`, and `RLIMIT_FSIZE`.
   - Optionally run worker pools in containers (Kubernetes) with enforced CPU and memory limits and GPU device plugin.

3. **Leases & Heartbeat**
   - Leases are persisted with TTL in orchestrator DB and require periodic heartbeat to extend.
   - Reclaimer/XCLAIM logic picks up orphaned jobs and reassigns them after lease expiry.

4. **Kill-on-OOM & NVML Watchdog**
   - `kill_on_oom` policy disables or enables forced cleanup of processes that cause GPU OOM or other host OOM conditions.
   - NVML watchdog (pynvml script) provides debugging and capture of GPU state on error.

5. **DLQ & Retries**
   - Jobs with transient errors are retried with exponential backoff; after N attempts they go to DLQ and raise alerts.

6. **Autoscaling & Admission backoff**
   - Autoscaler scales worker pools by queue backlog and resource availability.
   - Admission control delays (or rejects) new jobs when resources are saturated.

7. **Fair-share Scheduling**
   - Pools are tracked per agent and per group with policy constraints: `max_memory_per_agent_mb` and `max_total_workers`.

---

## Observability + Runbook Items

**Metrics to expose:**
- `orchestrator_job_processing_duration_seconds` (by job_type)
- `editorial_dispatch_total{method}`
- `orchestrator_lease_active_total`
- `job_dispatch_failures_total{reason}`
- `nvml_event_count` and `nvml_sample_stats`
- `consumer_lag_{topic}` for event backlogs

**Alerts to raise:**
- Consumer lag growing and increasing (indicates backlog / autoscale issue).
- `kill_on_oom` events or NVML exceptions logged.
- Lease saturation > 80%.
- Job failure rate exceeding threshold (e.g., 5%).

**Runbook:**
- Steps to force-evict pool and drain cluster.
- Steps to free leases and reassign jobs on leader failure.
- Emergency action steps for GPU OOM or host low-memory scenarios.

---

## Implementation Roadmap (Incremental)

1. **Quick wins (0–2 wks)**
   - Implement worker subprocess RLIMIT enforcement & tests.
   - Add `min_memory_mb` and `max_cpu_seconds` metadata to the job schema and enforce admission checks.
   - Add `orchestrator_jobs` fail/attempt counters and DLQ handling.

2. **Medium-term (2–6 wks)**
   - Implement `editorial_dispatcher` worker that consumes `editorial.decisions` and publishes `job.dispatch` topics.
   - Implement `job.dispatch` consumer and transition orchestrator workers to that path.
   - Add Prometheus metrics & alerts.

3. **Long-term (6–12 wks)**
   - Autoscaler improvements for worker pools (k8s/HPA/KEDA integration).
   - Deploy worker pools in containers with enforced `requests/limits` and GPU plugin.
   - Migrate to a Kafka/Redpanda + Schema Registry setup, with replay and compaction support.

---

## Tests and Validation

- Unit tests verifying RLIMIT (child process killed on exceed), admission control logic (insufficient RAM/GPU rejects), and reclaimer action for expired leases.
- Integration tests simulating a scheduled crawl load and measuring scaling behavior + no unbounded backlog.
- Load & chaos tests to simulate GPU OOMs and verify reclaimer cleans up and metrics/alerts fire.

---

## Migration Considerations

- Implement dual-write (legacy Redis + new event bus) temporarily to verify parity during migration.
- Add `CHIEF_EDITOR_DISPATCH_MODE` feature toggle to allow for canonical migration without rollback risk.
- Keep DB as a final authoritative store for articles, but use event streams for orchestration and tracing.

---

## Example Code Snippets

**Worker: RLIMIT subprocess spawn (Python)**

```python
import resource, os, signal, time

def spawn_limited_child(handler_callable, mem_mb, cpu_seconds, payload):
    pid = os.fork()
    if pid == 0:
        # child
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024**2, mem_mb * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
        try:
            handler_callable(payload)
        except Exception:
            os._exit(2)
        os._exit(0)
    else:
        start = time.time()
        while True:
            pid_done, status = os.waitpid(pid, os.WNOHANG)
            if pid_done != 0:
                return status
            if time.time() - start > cpu_seconds + 10:
                os.kill(pid, signal.SIGKILL)
                return -9
            time.sleep(0.1)
```

**Admission Check (pseudo)**

```python
import psutil

def admit_job(min_memory_mb):
    if psutil.virtual_memory().available < (min_memory_mb * 1024**2):
        return False
    return True
```

---

## Final Notes

- This proposal aims to keep minimal coupling between decision maker and executors: Chief Editor should not be responsible for dispatching jobs at scale. The `editorial_dispatcher` is a central, small piece that handles policy routing safely.
- The event-driven approach (Kafka/Redis) gives us scalability and replays for debugging and reprocessing events.
- With staged incremental changes (RLIMIT & admission checks first), the system can achieve a safer, more scalable pipeline without major disruption.

If you'd like, I can begin with the immediate implementation tasks (worker RLIMITs and admission control) along with unit/integration tests on a small feature branch. Let me know and I'll start the PR and tests.

*End of proposal.*
