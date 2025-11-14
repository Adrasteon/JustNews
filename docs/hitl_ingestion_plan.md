# HITL Ingestion Plan (Throughput-first)

This document captures the design and operational policy for the Human-In-The-Loop (HITL) ingestion point in the JustNews crawler pipeline. The goal is to maximize the number of quality articles placed into the database quickly while maintaining traceability and auditability. This plan is intentionally throughput-first: human annotators make a simple decision (Not news / Messy news / Valid news) and the system optimistically ingests when appropriate.

## Purpose & scope

- Place a lightweight HITL decision point in the crawler pipeline at the candidate detection stage.
- Keep the decision space deliberately small: `not_news`, `messy_news`, `valid_news`.
- Prioritise fast decisions and optimistic ingestion so articles reach the analyst stage quickly (where heavier analysis & cleanup happens).
- Collect labeled data for training models and improving automation.

## Current implementation status (Nov 2025)

- FastAPI HITL service is deployed with SQLite persistence, MCP Bus registration, and automated forward-target health checks.
- Candidate labeling UI consumes `GET /api/next`, while annotator submissions flow through `POST /api/label` with retrying ingest dispatch to downstream MCP tools.
- QA operations now include queue health monitoring, Prometheus metrics, reviewer endpoints (`/api/qa/pending`, `/api/qa/history`, `/api/qa/export`), and alert thresholds driven by environment toggles.
- MCP tool router (`POST /call`) exposes `receive_candidate`, `submit_label`, and `fetch_stats` for direct bus invocations; candidate fan-out is configurable via `HITL_CANDIDATE_FORWARD_*` settings.
- Training forward path streams labels to the training system via the `training_system.receive_hitl_label` MCP tool when `HITL_TRAINING_FORWARD_*` toggles are enabled.

## Contract (inputs, outputs, acceptance)

- Input: CandidateEvent (JSON) from crawler with fields: id, url, site_id, extracted_title, extracted_text, raw_html_ref, features (link_density, word_count, images_count), crawler_ts, crawler_job_id.
- Outputs:
  - Immediate ingestion request for `valid_news`.
  - Immediate optimistic ingestion request for `messy_news` with a `needs_cleanup` flag so analysts can prioritise cleanup.
  - No ingestion for `not_news` (persist for training/audit).
  - Training LabelEvent published for every human label.
- Success criteria (throughput-first):
  - Average annotator decision time ≤ 10s.
  - Label → ingest job enqueue latency ≤ 2s.
  - Sample 5% of human-labeled `valid_news`/`messy_news` for QA; target failure rate < 2%.
  - Training data available to retrain pipeline within ≤ 5 minutes of labeling.

## High-level architecture

- Crawler (unchanged extraction) publishes `crawler.candidate` events to the shared MCP Bus.
- HITL Service (new):
  - registers with MCP Bus on startup, validates downstream forward targets, persists candidates, prioritises queue, serves annotator UI via REST/WebSocket, accepts labels, publishes LabelEvents, and enqueues ingest jobs through the bus.
  - exposes env knobs (`MCP_BUS_URL`, `HITL_AGENT_NAME`, `HITL_SERVICE_ADDRESS`, `HITL_FORWARD_*`, `HITL_CANDIDATE_FORWARD_*`, `HITL_TRAINING_FORWARD_*`) so staging and production endpoints can be configured without code edits.
  - surfaces queue depth, QA backlog, and ingest dispatch metrics via Prometheus-compatible gauges and counters wrapped in `JustNewsMetrics`.
  - continuously samples QA queue health and raises warnings when backlog or failure rates exceed configured thresholds.
- Annotation UI (new): fast, single-key, low-latency web UI for annotators.
- Ingest pipeline: consumes ingest jobs and writes articles to DB; honours `needs_cleanup` flag and `ingestion_priority`; receives payloads via MCP tool calls with retry/backoff.
- Training pipeline: subscribes to `training.labels`, accumulates labels for incremental and full retraining.

## Data model (recommended schema additions)

Tables (minimal):

- `hitl_candidates`
  - id: uuid PK
  - url: text
  - site_id: text
  - extracted_title: text
  - extracted_text: text
  - raw_html_ref: text
  - features: jsonb
  - candidate_ts: timestamptz
  - crawler_job_id: text
  - status: enum('pending','in_review','labeled','skipped')
  - ingestion_priority: integer DEFAULT 0
  - suggested_label: text NULL
  - suggested_confidence: real NULL

- `hitl_labels`
  - id: uuid PK
  - candidate_id: uuid FK -> hitl_candidates
  - label: text CHECK IN ('not_news','messy_news','valid_news')
  - cleaned_text: text NULL
  - annotator_id: text NULL
  - created_at: timestamptz
  - source: text (ui/manual, auto/model)
  - treat_as_valid: boolean DEFAULT false
  - needs_cleanup: boolean DEFAULT false
  - qa_sampled: boolean DEFAULT false
  - ingest_enqueued_at: timestamptz NULL
  - ingestion_status: text NULL

- `hitl_qa_queue`
  - id: uuid PK
  - label_id: uuid FK -> hitl_labels
  - candidate_id: uuid
  - created_at: timestamptz
  - review_status: enum('pending','pass','fail')
  - reviewer_id: text NULL
  - notes: text NULL
  - reviewed_at: timestamptz NULL

- `model_versions` / `training_runs` (optional) to track datasets and metrics.

Use JSONB fields where useful to avoid schema churn. Index by status and candidate_ts for queue operations.

## Message topics / events

- `crawler.candidate` — CandidateEvent (crawler -> HITL)
- `training.labels` — LabelEvent (HITL -> training)
- `ingest.jobs` — IngestJob (HITL -> ingest pipeline)

CandidateEvent (example fields):

```
id, url, site_id, extracted_title, extracted_text, raw_html_path, features, crawler_ts, crawler_job_id
```

LabelEvent (example fields):

```
candidate_id, label, cleaned_text, annotator_id, created_at, source, treat_as_valid, needs_cleanup, qa_sampled, extra
```

## Ingestion policy (throughput-first)

Goal: get quality articles into the DB fast; rely on analysts downstream for heavy cleanup.

Default policy:

- `valid_news`
  - treat_as_valid = true
  - needs_cleanup = false
  - enqueue ingest job immediately with high priority
- `messy_news` (optimistic path)
  - treat_as_valid = true
  - needs_cleanup = true
  - enqueue ingest job immediately with medium priority; include cleaned_text when provided
  - mark for post-ingest cleanup/analyst prioritisation
- `not_news`
  - treat_as_valid = false
  - do not enqueue ingest; persist for training/audit

QA & safeguards:

- Randomly sample ~5% of human-labeled `valid_news` / `messy_news` for manual QA.
- If sampled failure rate exceeds threshold (e.g., 2%), throttle optimistic `messy_news` ingestion and increase QA sampling.

Auto-label fallback (when annotators are unavailable):

- model_confidence >= 0.98: auto-label and ingest accordingly
- 0.85 <= confidence < 0.98: route to HITL but prefill suggestion
- confidence < 0.85: hold for HITL

Tune thresholds based on observed precision/recall.

## UI / UX guidelines (throughput-optimised)

- Single-screen candidate view: title, extracted text (sanitised plain text), editable cleaned-text field.
- Hotkeys:
  - `V` = Valid news (ingest immediately)
  - `M` = Messy news (optimistic ingest + needs_cleanup)
  - `N` = Not news (discard / training)
  - `S` = Submit and next
  - Arrow keys = navigation
- Prefill model suggestion (label + confidence); one-key accept.
- Batch mode: fetch a small batch (e.g., 10) for rapid sequential labeling to reduce roundtrip latency.
- Auto-advance after label; show queue depth and small throughput metrics.
- Annotator login: capture `annotator_id` for audit.

## Crawler integration & flow changes

- Crawler publishes CandidateEvent to `crawler.candidate` topic instead of direct ingestion.
- HITL service persists candidate and adds to a prioritized queue.
- Queue prioritisation strategies (tuneable): prefer short articles for throughput; or sample varied lengths for balanced dataset.
- If backlog is high, enable more aggressive auto-labeling or increase model prefill confidence thresholds.

## Model strategy (practical)

- Start with the model as an assistant that pre-suggests labels/cleaned snippets to annotators.
- Retrain cadence:
  - incremental mini-batch retrain every 5–15 minutes (for fast adaptation)
  - full retrain nightly with validation and versioning
- Online learners (Vowpal Wabbit or partial_fit) can be used for immediate updates but keep periodic full retrain to avoid drift.
- Use model in production to auto-label very high-confidence candidates and prefill suggestions for borderline candidates.

## Monitoring & metrics (throughput-first)

- Annotator metrics: labels/hour, avg decision time (target ≤10s), per-annotator error rate via QA samples.
- Pipeline metrics: queue depth (`hitl_pending_candidates`, `hitl_in_review_candidates`, `pending_total`), label→ingest latency (target ≤2s), ingest backlog size (`hitl_ingest_backlog`), % auto-ingested.
- MCP integrations: `hitl_mcp_candidate_events_total`, `hitl_mcp_label_events_total`, forward-target gauges (`hitl_forward_registry_available`, `hitl_forward_agent_available`, `hitl_candidate_forward_agent_available`, `hitl_training_forward_agent_available`).
- Ingest dispatch health: counters for attempts/success/failure (`hitl_ingest_dispatch_*`) and duration timings to profile downstream MCP calls.
- QA sampling failure rate and automated triggers (throttle optimistic ingestion when it rises); dedicated gauges `hitl_qa_pending_total`, `hitl_qa_failure_rate`, and windowed review counts support alerts.
- QA queue health exposed to dashboards and reviewer tooling via the stats endpoints and Prometheus gauges; monitor `HITL_QA_BACKLOG_ALERT_THRESHOLD` and `HITL_QA_FAILURE_RATE_ALERT_THRESHOLD` to tune notifications.

## Edge cases & mitigations

- Multiple articles in one page: allow annotators to select boundaries in the cleaned_text; optionally create multiple candidate records per page.
- JS-heavy pages: use headless rendering prior to extraction; store screenshot for annotators if useful.
- Spam/malicious pages: sanitise previews, quarantine clearly malicious or malformed pages.
- Annotator quality: periodic calibration with gold-standard examples, limit session lengths, rotate tasks.

## Minimal schema migration & API endpoints (first implementation)

Schema changes (minimal, low-risk):

- Add columns to `hitl_candidates`:
  - `ingestion_priority` integer DEFAULT 0
  - `suggested_label` text NULL
  - `suggested_confidence` real NULL

- Add columns to `hitl_labels`:
  - `treat_as_valid` boolean DEFAULT false
  - `needs_cleanup` boolean DEFAULT false
  - `qa_sampled` boolean DEFAULT false
  - `ingest_enqueued_at` timestamptz NULL
  - `ingestion_status` text NULL

API endpoints (HITL service):

- `POST /api/candidates` — crawler -> persist candidate
- `GET /api/next?annotator_id=...&batch=N` — get N next prioritized candidates
- `POST /api/label` — submit a label (payload: candidate_id, label, cleaned_text, annotator_id); returns `{enqueue_ingest: bool, ingest_job_id: uuid|null}`
- `POST /api/qa/review` — QA reviewer marks a sampled label as pass/fail and records notes
- `GET /api/qa/pending` — list pending QA entries with joined candidate/label context (pagination via `limit`)
- `GET /api/qa/history?status=...&limit=N` — historical QA records filtered by status (default `all`)
- `GET /api/qa/export?limit=N` — streaming CSV export of QA queue data for audits
- `GET /api/stats` — queue depth, recent throughput, QA sampling counts, latency summaries
- `POST /call` — MCP tool router exposing `receive_candidate`, `submit_label`, and `fetch_stats` handlers for bus-triggered workflows

These endpoints enable the crawler, annotator UI and ingest pipeline to integrate with HITL.

Service integration details:
- MCP Bus registration runs automatically; configure `MCP_BUS_URL`, `HITL_AGENT_NAME`, and `HITL_SERVICE_ADDRESS` per environment.
- Downstream ingest dispatch is controlled via `HITL_FORWARD_AGENT` and `HITL_FORWARD_TOOL` so targets can be changed without redeploying code.
- Optional candidate fan-out is enabled by `HITL_CANDIDATE_FORWARD_AGENT` and `HITL_CANDIDATE_FORWARD_TOOL` for any additional consumers.
- Training-forward plumbing is controlled by `HITL_TRAINING_FORWARD_AGENT` and `HITL_TRAINING_FORWARD_TOOL`; point these at `training_system` / `receive_hitl_label` to stream labels automatically.
- Use `HITL_DB_PATH` to select the SQLite file path (defaults to `agents/hitl_service/hitl_staging.db`).
- Supply `HITL_PRIORITY_SITES` (comma-separated) to boost key sources in the queueing heuristic.
- Configure QA monitoring via `HITL_QA_BACKLOG_ALERT_THRESHOLD`, `HITL_QA_FAILURE_RATE_ALERT_THRESHOLD`, `HITL_QA_FAILURE_MIN_SAMPLE`, and `HITL_QA_MONITOR_INTERVAL_SECONDS` to align with reviewer capacity.
- Ensure the downstream ingest agent exposes an MCP tool that accepts the `/api/label` `ingest_payload` schema.

## QA sampling & audit

- Default sample rate: 5% of human `valid_news` and `messy_news` labels.
- QA workers evaluate sampled items from `hitl_qa_queue` and record pass/fail decisions via `POST /api/qa/review`; failures increment the QA-failure metric and may trigger throttles.
- Reviewers can pull worklists with `GET /api/qa/pending`, audit recent decisions via `GET /api/qa/history`, and generate CSV snapshots with `GET /api/qa/export` for offline analysis.
- Monitor `qa_pending`, `qa_sampled_today`, and `hitl_qa_failure_rate` from `/api/stats` and Prometheus to ensure review capacity matches inflow.

## Rollout plan (short)

1. Deploy HITL service + UI in staging. Annotators label until 10k labeled examples are obtained.
2. Start with `messy_news` -> optimistic ingest policy and QA sampling at 5%.
3. Monitor QA sample failure rate and throughput metrics. If QA failure > threshold (e.g., 2%) reduce optimism for `messy_news`.
4. Train model after initial dataset and enable auto-labeling at high confidence. Use prefill suggestions for borderline candidates.
5. Gradually raise auto-labeling coverage while keeping QA sampling until model performance is acceptable.

## Low-risk immediate implementation items

- Create DB migration SQL to add recommended fields.
- Scaffold a minimal FastAPI app with endpoints above and a simple in-memory queue for local testing.
- Add a single-file static UI for batch labeling with hotkeys that posts to the API.
- Implement QA sampler (5%) in the HITL service that marks `qa_sampled` and records results.
- Store schema migrations under `agents/hitl_service/migrations/` and apply them when moving beyond the staging SQLite file.

## Next steps (recommended)

1. Enable `HITL_TRAINING_FORWARD_*` in staging and validate the `receive_hitl_label` pipeline with Prometheus metrics before production rollout.
2. Integrate the reviewer dashboard with the new QA listing and export endpoints; add automated coverage to prevent regressions.
3. Expand monitoring dashboards/alerts to include new Prometheus gauges and ingest dispatch counters; validate thresholds in staging before production rollout.
4. Continue tuning annotator UI throughput (batch sizing, hotkeys) based on live telemetry and QA outcomes.

---
