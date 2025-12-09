---
title: JustNews Technical Architecture (canonical)
description: System-level architecture, component responsibilities and implementation status tracker for the JustNews platform.
tags: [architecture, system, operations]
status: current
last_updated: 2025-12-09
---

# JustNews — Technical Architecture (canonical)

This document is the canonical, single-file architectural overview for the JustNews system. It synthesizes the high-level design and maps ongoing implementation/status work so teams can quickly find the right subsystem documentation and current progress.

Purpose:
- Provide a single concise system diagram + component responsibilities
- Surface the current implementation status for each major area (so progress can be tracked)
- Link to authoritative subsystem docs and tests for deeper detail

Audience: architects, engineers, operators and program managers working across the project.

---

## 1. System overview

JustNews is a distributed, multi-agent news analysis platform with strong separation of concerns:

- Crawling & fetch (scalable fetchers, raw HTML snapshotting)
- Archive & ingestion (raw_html persistence, normalization into canonical records)
- Parsing & extraction (content structuring, metadata extraction)
- Reasoning & editorial agent chain (agent-driven editorial reasoning, fact-checking, synthesizer)
- Publishing (lightweight publisher application and ingestion for produced articles)
- Orchestration (GPU Orchestrator for resource leasing and job queues)
- Observability & monitoring (Prometheus, Grafana dashboards, traces, alerts)
- Training & model store (ModelStore and training pipelines)

Data & control plane:
- Data flows: crawl -> archive/raw_html -> ingest -> normalized rows -> editorial harness -> publish
- Control plane: MCP Bus + orchestrator + job queues and admin endpoints

High-level diagram (visual):

![System overview diagram](./diagrams/assets/system_overview.svg)

GPU & Model compute: Editorial & other agents request orchestration (policy/leases) or submit jobs -> agents/gpu_orchestrator -> worker pools (Redis Streams)

---

## 2. Important repository landing pages (authoritative)
- Repo-level: `README.md` (root) — quick start and high-level summary
- Canonical docs index: `docs/README.md` — documentation catalogue and navigator
- System status / program-level plan: `COMPREHENSIVE_REFACTORING_ANALYSIS.md` — high-level refactor/program progress
- Live-run E2E plan: `docs/live-run-plan.md` — staged end-to-end plan for crawl -> publish validation
- Orchestrator design & runbook: `docs/workflow_management.md` — persistent orchestration & job lifecycle (GPU Orchestrator)
- Editorial ↔ Orchestrator crosswalk: `docs/editorial-orchestrator-crosswalk.md`

These files should be consulted in combination to get both the operational roadmap and the detailed subsystem specifications.

---

## 3. Component responsibilities & implementation status
Status legend:
- ✅ Completed
- 🟢 Production-ready / well-instrumented
- 🟡 In-progress / partially implemented
- ⚠️ Outstanding / requires work

For each major component below we show: short description, current status, evidence (file/tests), and suggested next actions.

### 3.1 Crawling & fetch
- Description: crawler agents fetch pages and store raw HTML snapshots and extraction metadata.
- Status: 🟢 Implemented - robust fetchers + raw_html persistence
- Evidence: `agents/crawler/`, `agents/crawler/extraction.py`, `scripts/dev/canary_urls.txt`
- Next steps: periodic canary verification dashboards and ingest gating automation.

### 3.2 Archive & Ingestion
- Description: ensure raw_html snapshots are kept and ingestion converts snapshots to normalized records.
- Status: 🟡 In-progress — pipeline exists with tests, but DB visibility & Grafana gating need stronger wiring
- Evidence: `agents/archive/ingest_pipeline.py`, `agents/archive/raw_html_snapshot.py`, tests `tests/agents/test_archive_ingest_pipeline.py`
- Next steps: finalize Grafana panels (done: `docs/grafana/ingest-archive-dashboard.json` added), add CI metric gating on canary design.

### 3.3 Parsing & Extraction
- Description: content extraction (Trafilatura-first strategy) and structured field extraction.
- Status: 🟡 Partially implemented — deterministic canary fixtures exist; more edge cases needed
- Evidence: `tests/parsing/test_canary_articles.py`, `tests/fixtures/canary_articles/`
- Next steps: broaden fixtures for authors/dates edge cases and link to normalized feed tests.

### 3.4 HITL service / Editor label flows
- Description: human-in-the-loop labeling and ingest-enqueue behavior between crawler → ingest → editorial harness.
- Status: 🟢 Implemented with metrics & UI
- Evidence: `agents/hitl_service/app.py`, `agents/hitl_service/README.md`, frontend static files and metric hooks
- Next steps: ensure integrations are fully reflected in Grafana and add DB gating checks for ingest enqueues.

### 3.5 Editorial harness & reasoning agents
- Description: agent chain that reads normalized articles and outputs drafts with acceptance/followup checks.
- Status: 🟡 In-progress / production-ready tests present
- Evidence: `agents/common/editorial_harness_runner.py`, `scripts/dev/run_agent_chain_harness.py`, tests under `tests/agents/common/` and CI workflows (`.github/workflows/editorial-harness.yml`)
- Next steps: finish metrics wiring and record drafts in publisher checklist and provenance/audit logs.

### 3.6 Publisher application (lightweight)
- Description: Django-based publisher for vetting, storing and rendering published articles; exposes metrics & audit API.
- Status: 🟢 Implemented and covered by e2e tests
- Evidence: `agents/publisher/` (manage.py, models, views), `tests/e2e/test_publisher_publish_flow.py`, `docs/grafana/publisher-dashboard.json`
- Next steps: harden auth/approval flows for production, extend audit logs and ingest validation.

### 3.7 GPU Orchestrator and worker pools
- Description: persistent orchestrator that manages leases, worker pools, Redis Streams, reclaimer and DLQ for GPU-bound jobs.
- Status: 🟡 In production PoC / core features implemented but production hardening outstanding
- Evidence: `agents/gpu_orchestrator/*` (`main.py`, `gpu_orchestrator_engine.py`, `worker.py`, `job_consumer.py`), tests `tests/e2e/test_orchestrator_real_e2e.py`, monitoring alert rules `monitoring/alerts/gpu_orchestrator_*.yml` and `docs/workflow_management.md`
- Next steps: finalize production Redis semantics (`XAUTOCLAIM`), idempotency hardening, runbook drills and soak tests.
 
 ![GPU orchestrator flow](./diagrams/assets/orchestrator_flow.svg)

### 3.8 Observability & Monitoring
- Description: Prometheus metrics, Grafana dashboards, alerts, traces and dashboards for editorial harness, publisher and orchestrator.
- Status: 🟢 Foundations implemented; wiring gaps remain
- Evidence: `docs/grafana/editorial-harness-dashboard.json`, `docs/grafana/publisher-dashboard.json`, `monitoring/dashboards/generated/system_overview_dashboard.json`, `monitoring/alerts/*`
- Next steps: ensure all ingest/raw_html counters are provisioned (added: `docs/grafana/ingest-archive-dashboard.json`), and tune alerts & CI gating.

### 3.9 Deployment & CI/CD
- Description: systemd-first deployments, CI workflows, release & packaging pipelines, docs-driven checks.
- Status: 🟢 Implemented; CI workflows present; E2E systemd-nspawn runners available
- Evidence: `infrastructure/systemd/*`, `Makefile`, `.github/workflows/*`, `COMPREHENSIVE_REFACTORING_ANALYSIS.md`
- Next steps: finalize release automation for orchestrator and publisher; add CI gating around canary metrics.

### 3.10 Configuration, Security & Compliance
- Description: Pydantic v2 centralized config, auth, RBAC and GDPR notes
- Status: 🟢 Implemented, audited
- Evidence: `config/`, `COMPREHENSIVE_REFACTORING_ANALYSIS.md`, `security/` and `docs/`
- Next steps: continued audits and operational checks.

### 3.11 Testing & quality
- Description: unit, integration & gated E2E tests (with opt-in GPU tests)
- Status: 🟢 Substantially implemented
- Evidence: `tests/` (unit/integration/e2e), `pytest.ini`, gating environment flags in `live-run-plan.md`
- Next steps: close remaining test failures and improve canary coverage.

---

## 4. How to read / maintain this doc
- This file should be the canonical, short system architecture view. For deep dives, consult subsystem docs listed at the top.
- Implementation status should be updated as part of PRs that change subsystem readiness. Suggested pattern: update the status legend entry and add a short “last_updated” note in the block.

Recommended status workflow:
1. Small change → subsystem doc + tests updated → PR updates this document (status & evidence) or the subsystem doc directly.
2. Larger milestones (e.g., production hardening) → update `COMPREHENSIVE_REFACTORING_ANALYSIS.md` and the subsystem page and add a short paragraph here.

---

## 5. Immediate priorities (coordination)
- Finalize ingest/raw_html metric wiring to Grafana + add CI gating on canary ingestion/publish metrics.
- Finalize GPU Orchestrator production hardening (reclaimer XCLAIM/XAUTOCLAIM semantics, idempotency tests, soak tests) and operator playbooks.
- Expand deterministic parsing fixtures for author and publish-date edge cases and add unit/integration tests.

---

If you want I can:
- Create an automated check that validates this doc's status blocks against tests/coverage (CI gating), or
- Draft a one-page operations runbook adapted from `workflow_management.md` for operator drills (evict/pause/drain), or
- Add a diagram (SVG/Mermaid) and link into `docs/README.md` and root `README.md`.
