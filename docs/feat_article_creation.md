# Feature: Article Creation Workflow (feat/article_creation)

## Summary

This document defines the workflow, implementation plan, and acceptance criteria for the `feat/article_creation` branch. The goal is to implement a robust pipeline that synthesizes unbiased, traceable articles from clustered articles, runs the result through a Critic and Fact-checker, optionally performs HITL review, and publishes approved articles to the JustNews website.

We aim to implement an MVP with safe defaults and meaningful tests, followed by incremental improvements and additional integrations.

---

## Scope (MVP)

- Input: cluster of articles (list of article IDs or a cluster ID) produced by existing clustering logic.
- Output: a new synthesized article persisted in MariaDB and Chroma, with full metadata and traceability.
- Integrations: Critic agent, optional fact-checker, Chief Editor review. External LLMs can be mocked in tests.
- Feature flags to prevent automatic publishing in production by default.

Out of scope (for this branch): full HITL UX polishing, advanced retraining integrations, or complex multi-agent coordination beyond the basic flow.

---

## Design & High-Level Flow

1. (Trigger) A `SYNTHESIZE_CLUSTER` job is created (API, scheduled job, or agent event).
2. `ClusterFetcher` queries Chroma and MariaDB to collect and deduplicate the articles for the cluster.
3. `SynthesisService` synthesizes a draft article using a model/prompt template and returns a structured `DraftArticle` object containing: `title`, `body`, `summary`, `quotes`, `source_ids`, `trace`.
4. Save draft to MariaDB (or `synthesized_articles` table); generate embedding and store in Chroma.
5. Send draft to `Critic` agent for assertions and policy checks; capture `critic_result`.
6. Call `FactChecker` and optional `Entity` identification services; capture `fact_check_status`.
7. If Critic or FactChecker fail, escalate to HITL or mark `needs_revision` and update metadata.
8. If passes and `CHIEF_EDITOR_REVIEW_REQUIRED` is `false`, publish; otherwise enqueue for review in `chief_editor` agent workflow.
9. On publishing: set `is_published=true`, record `published_at` and `published_by`, update Chroma and index in the content hosting layer.


---

## Data Model & Schema Changes

A. DB Model choices (Two options):

- Option A (extend `articles` table): add fields for synthesized metadata.
- Option B (new `synthesized_articles` table): dedicated table for synthesized content and traceability metadata.

MVP Recommendation: Extend the `articles` table with the following new fields to keep minimal migration surface.

Fields:
- `is_synthesized` BOOLEAN DEFAULT FALSE
- `input_cluster_ids` JSON or TEXT
- `synth_model` VARCHAR
- `synth_version` VARCHAR
- `synth_prompt_id` VARCHAR
- `synth_trace` TEXT (or JSON) — store model prompt, steps, summary of trace
- `critic_result` JSON (or TEXT)
- `fact_check_status` ENUM: `pending`, `passed`, `failed`, `not_checked`
- `is_published` BOOLEAN DEFAULT FALSE
- `published_at` DATETIME NULLABLE
- `created_by` VARCHAR: `agent:synthesizer` or `user:...`

Migrations:
- Add a migration script in `database/core/migrations/` with `CREATE, ALTER TABLE` to add the columns.
- Acceptance: DB migration should be idempotent and reversible, with zero downtime if possible.

Model Class Changes:
- Update `Article` (or add a `SynthesizedArticle` subclass) in `database/models/migrated_models.py` to serialize new metadata fields, and tests for to/from conversions.

Chroma Data: store `is_synthesized` flag in metadata for the vector to simplify discovery.

---

## Synthesis Service: Implementation Details

File/Module: `agents/synthesizer/service.py` (or under `agents/journalist/synthesizer.py`)

Responsibilities:
- Accept event payload { cluster_id | article_ids, options }
- Call `ClusterFetcher` to collect article content and metadata
- Build prompt using defined templates (templates stored in repo or DB; ensure version/ID captured)
- Call the configured synthesis model or use a fallback deterministic method in tests
- Return `DraftArticle` with trace and source IDs
- Log metrics and produce observability signals

Testing:
- Unit tests for the generator logic using small prompt templates & known inputs
- Integration test with mocks for LLMs and Chroma/MariaDB

Prompts & Config:
- Define prompt templates in `config/` or a `synth_prompts/` directory
- A small matrix of `SYNTHESIS_MODEL` config options

Edge handling and safety:
- Enforce `SYNTHESIS_MIN_CLUSTER_SIZE` (e.g., 3 articles default)
- Clean input text to remove PII and sanitize HTML
- If model returns hallucinated claims, `Critic` should mark for review or block publishing

---

## Critic & Fact-Check Integration

- After the draft is generated, call the `Critic` agent: `agent/critic` or module call: `agents/critic/validate()`.
- Capture `critic_result` JSON including issues, categories, severity.
- If Critic indicates `block` severity, set `status=needs_revision` and optionally escalate to HITL.
- Fact-check (optional): `agents/fact_checker/check_claims(draft_text, quotes)` to verify factual claims; store `fact_check_status`.

---

## Chief Editor / HITL Workflow

- If `CHIEF_EDITOR_REVIEW_REQUIRED=1`, the system should place the draft in a Chief Editor review queue with a reference to `id` and metadata.
- Chief Editor should be able to edit the draft and accept/reject/publish. This requires frontend hooks and endpoints.
- Provide `GET /api/v1/articles/drafts` and `POST /api/v1/articles/:id/publish` for Chief Editor actions.

---

## API Endpoints & Scripts

- POST `/api/v1/articles/synthesize` { cluster_id | article_ids, options } -> returns a job_id / draft.
- GET `/api/v1/articles/synthesize/{job_id}` -> job status + preview + critic_result
- GET `/api/v1/articles/:id/draft` -> retrieve a draft article
- POST `/api/v1/articles/:id/publish` -> publish (Chief Editor or automated if gate allows)

Script for debugging:
- `scripts/synthesize_cluster.py` should exist to exercise the service locally and return the draft

---

## Test Strategy

- Unit Tests:
  - `tests/agents/synthesizer/test_synthesis_service.py`: verify shaping of draft
  - `tests/database/test_synthesized_article_model.py`: model serialization
  - `tests/database/test_chromadb_utils` integration points using mocks

- Integration Tests:
  - `tests/integration/test_article_creation_flow.py` marked with `integration` marker: a simulated run from cluster -> draft -> critic -> saved; requires integration fixtures.

- Performance Tests (later):
  - `tests/database/test_dual_database_performance.py` style tests for large cluster sizes

---

## CI & Preflight

- Add unit tests to run as part of existing CI suite
- Add an `integration` marked job in `.github/workflows/pytest.yml` that runs the integration workflows in a dedicated runner
- Feature flags: use `SKIP_PREFLIGHT` and `ARTICLE_SYNTHESIS_ENABLED` controls for dev vs CI

---

## Observability & Metrics

- Log events: `synthesis_job_id`, `cluster_id`, model/version used, start/end times, `critic_result`, `fact_check_status`, `published` status
- Metrics:
  - `synthesis_jobs_started` (counter)
  - `synthesis_jobs_failed` (counter)
  - `synthesis_jobs_published` (counter)
  - Traces for model latency (gauge)

---

## Security & Ethics

- Use Critic agent to monitor and block biased content or policy violations
- Ensure generated content is tagged as machine-generated: `metadata.machine_generated` for transparency
- Ensure sensitive personal data is redacted in the input and in the final article

---

## Rollout Plan

- Phase 1: Dev/MVP
  - Implement the service and tests, allow manual synthesis via API/UI, run tests & smoke tests
  - Acceptance: basic end-to-end flow with mocked LLM, Critic integration, storage of metadata

- Phase 2: Staging
  - Enable feature flag for a small percentage of clusters and route to Chief Editor review
  - Acceptance: Chief Editor flows working, logs and metrics present, no production publishes

- Phase 3: Production (Canary)
  - Run on low traffic sample with auto-CR and optionally limited publish
  - Acceptance: stable metrics and no critical issues

- Phase 4: Production full rollout
  - Enable synthesis for more clusters, monitor metrics, and expand checks

---

## Acceptance Criteria

- Unit tests and integration tests pass for the implemented modules
- Draft contains: title, body, summary, input cluster ids
- `critic_result` present and used to gate the publishing step
- The synthesized article is stored in the DB/Chroma with traceable metadata
- Chief Editor can review, edit, and publish draft (with proper audit logs)

---

## Work Items (MVP prioritized)

- Implement DB migration & models
- Implement `ClusterFetcher`
- Implement `SynthesisService` skeleton with a deterministic test stub
- Add Critic integration & simple Fact-checker stub
- Add API endpoints and `scripts/synthesize_cluster.py`
- Add Chief Editor review and publish endpoints (backend only for MVP)
- Add unit tests and a basic integration test
- Add observability metrics and feature flags

---

## Owner & Timeline

- Owner: `agents/journalist`, `agents/synthesizer`, and `database` owners together
- Timeline: break down into 2-week sprints:
  - Sprint 1: Data model + SynthesisService + ClusterFetcher + Unit tests
  - Sprint 2: Critic & Fact-check integration + API endpoints + Integration tests
  - Sprint 3: Chief Editor review flow + UI hooks + Staging rollout

---

## Stretch Goals (post-MVP)

- Multi-language generation + token-level claim-tracking
- Model fine-tuning data pipeline for redesigning model
- Feedback loop from Chief Editor decisions back to model prompts

---

## References

- `database/models/migrated_models.py`
- `database/utils/migrated_database_utils.py`
- `agents/synthesizer` (new)
- `agents/critic` (existing)
- Existing crawling, clustering (Chroma) and embedding utilities

---

End of document.
