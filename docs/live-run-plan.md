## JustNews Live-run E2E Plan

This document contains the staged plan to get JustNews working end-to-end — from crawl -> ingestion -> parsing -> editorial -> publish — with measurable checks and debugging guidance. This file is generated from an actionable plan and mirrors the roadmap for the `dev/live-run-tests` branch.

High-level goals:

- Crawl agents fetch URLs and reliably store raw HTML
- Ingest and normalize raw HTML into records
- Parse structure and extract necessary fields
- Agents (journalist, fact_checker, synthesizer) produce a draft with checks
- Publish a final article and verify accessible content
- Observe and measure the success/failure of each stage with dashboards and counters

Stages and success criteria:

1. Stage 0 — Setup & baseline
   - Reproducible branch and deterministic dev environment
   - Services: MariaDB, Redis, Chroma
   - Tests: unit + smoke tests run locally

2. Stage 1 — Crawl & fetch verification
   - Verify fetchers write raw HTML and metadata
   - Metrics: fetch rate, success ratio, latency

3. Stage 2 — Ingestion & normalization
   - Normalize raw HTML into canonical records
   - Metrics: ingest success rate, processing time

4. Stage 3 — Parsing & structure extraction
   - Extract title, author, publish_date, body
   - Tests validate extraction correctness on canary dataset

5. Stage 4 — Reasoning, fact-check and editorial agents
   - Agent chain produces final article draft with checks
   - Metrics: draft acceptance rate, fact-check flags

6. Stage 5 — Publishing & end-to-end verification
   - Publish final article, validate site endpoint and content
   - KPIs: e2e time, publish success

7. Observability & test harness
   - Metrics, traces (correlation IDs), dashboards
   - Canary dataset for E2E automation

8. Rollouts & safety
   - Staging gating, manual approvals, audit logs

Immediate repo activities performed on branch `dev/live-run-tests`:

- Add `docs/dev-setup.md` — reproducible local setup + common commands
- Add `scripts/dev/canary_urls.txt` — minimal canary targets for controlled runs
- Add `tests/smoke/test_stage0_env.py` — fast smoke tests to validate the dev baseline

Follow the README and `docs/dev-setup.md` to start reproducing locally and iterate through stages.
