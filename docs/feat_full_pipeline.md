# Feature: Full Article Pipeline (feat/full_pipeline)

## Overview

This feature unifies the full end-to-end article pipeline into a single documented flow and includes the runtime configuration, gating, and observability required to safely synthesize and publish articles. It builds on the `feat/article_creation` work (ClusterFetcher, Analyst, Fact-Checker, Reasoning, Synthesizer, Critic, Chief Editor) and extends it with operational guidance, integration tests, and deployment considerations.

This document is intended to be the canonical reference for the full pipeline delivered on the `feat/full_pipeline` branch.

---

## Goals

- Provide an audited, traceable, and gate-able synthesis pipeline for clustered news articles.
- Ensure synthesized drafts undergo mandatory per-article fact-checking and post-synthesis fact-checking before publish.
- Support both persistence strategies (Option A: extend `articles` table, Option B: `synthesized_articles` table) and a database-backed job store.
- Expose runtime admin controls via the Dashboard for gating feature flags and persistence method.
- Provide reliable integration tests and CI gating to avoid accidental auto-publish in production.

---

## High-Level Flow

1. Trigger (API, scheduled job, or orbit event) begins a `SYNTHESIZE_CLUSTER` job.
0. Pre-flight: Web crawl & scrape — the pipeline starts here. `CrawlerEngine` (`agents/crawler/crawler_engine.py`) or the `GenericSiteCrawler` discovers article URLs, applies paywall detection and initial heuristics, then calls the `memory` agent (`/ingest_article`) to persist candidate articles. The earliest decision is whether a page qualifies as a valid article via `agents/crawler/extraction.extract_article_content()` (word count, text/html ratio), `skip_ingest` (paywalled), and `needs_review` flags.
2. `ClusterFetcher` collects deduplicated articles for the given cluster.
3. `Analyst` runs per-article claim extraction and a per-article `source_fact_check` using `FactCheckerEngine`.
4. `Reasoning` agent receives the `AnalysisReport` and produces a `reasoning_plan` with prioritized sources, outline, and claims.
5. `Synthesizer` constructs a draft using the `reasoning_plan` and `Analyst` outputs and returns a `DraftArticle` structure.
6. `Critic` reviews the draft for policy and style; the draft is then sent through a mandatory draft-level fact-check.
7. If the draft passes fact-check and Critic constraints, and publishing gates allow, the article is auto-published or queued for Chief Editor review.
8. On publish the system records `is_published`, `published_at`, updates Chroma embeddings, and logs tracing/metrics.

Notes:
- `min_fact_check_percent_for_synthesis` controls whether a cluster proceeds to synthesis at all.
- `require_draft_fact_check_pass_for_publish` controls whether `draft_fact_check` can block publishing.
- `chief_editor_review_required` forces HITL review independent of fact-check status.

---

## Major Components

- `agents/cluster_fetcher/ClusterFetcher` — harvests cluster content and normalizes article records.
 - `agents/crawler/CrawlerEngine` & `GenericSiteCrawler` — initial webcrawl, scraping and article extraction. They apply a multi-tier extraction pipeline (`agents/crawler/extraction.py`) and simple heuristics that mark `needs_review` when the content is short (below `ARTICLE_MIN_WORDS`) or has a low text-to-HTML ratio (`ARTICLE_MIN_TEXT_HTML_RATIO`). Paywall detection and `skip_ingest` are used to avoid ingesting behind-paywall pages unless explicitly permitted.
- `agents/analyst/AnalystEngine` — extracts claims, runs per-article fact checks, and outputs `AnalysisReport` with `source_fact_checks` and `cluster_fact_check_summary`.
- `agents/reasoning/Reasoning` — converts `AnalysisReport` into a `reasoning_plan` used to guide synthesis.
- `agents/synthesizer/SynthesizerEngine` — synthesizes the article draft from the plan, records model traces, and creates a DB-backed job when async.
- `agents/critic` — policy validation and editorial guideline checks.
- `agents/fact_checker/FactCheckerEngine` — claim verification for both pre-flight (`source_fact_check`) and post-synthesis draft checks.
- `agents/chief_editor` — HITL queue and review/publish APIs.
- `database` migrations 004/005/006 — schema changes for extended `articles`, new `synthesized_articles`, and job store.

---

## Admin Controls & Dashboard

The Dashboard offers a small Admin UI for runtime toggles (under `Settings -> Publishing`) with these options:
- `Require draft fact-check pass for publish` — set `agents.publishing.require_draft_fact_check_pass_for_publish`.
- `Require chief editor review` — set `agents.publishing.chief_editor_review_required`.
- `Synthesized article storage` — set `system.persistence.synthesized_article_storage` with choices: `extend` | `new_table`.

Endpoints:
- `GET /admin/get_publishing_config` — returns runtime flags and persistence choice.
- `POST /admin/set_publishing_config` — sets config via the `ConfigurationManager` and persists when requested.

Security: These endpoints should be protected in production (internal IP, API key or service-token-based access).

---

## Persisted Data & Traceability

Modeling choices are documented in `feat_article_creation.md`, but the pipeline enforces full traceability: every synthesized article draft stores metadata like `synth_trace`, `critic_result`, `analysis_summary`, `source_fact_checks`, `reasoning_plan_id`, and `fact_check_trace`.

Chroma: store `is_synthesized` metadata on embeddings to help retrieval & housekeeping.

Migration summary:
- `004_add_synthesis_fields.sql` — adds synth fields to `articles` for Option A.
- `005_create_synthesized_articles_table.sql` — Option B table layout.
- `006_create_synthesizer_jobs_table.sql` — DB-backed job store to ensure durable async jobs.

---

## Fact-Checking & Critic Policy

- Fact-checking is mandatory: both per-source (`source_fact_checks`) and draft-level.
- `SourceFactCheck` verdict mapping: `>= 0.8 => passed`, `0.6-0.79 => needs_review`, `< 0.6 => failed` (default thresholds — configurable).
- Draft `fact_check_status` can be `pending`, `passed`, `needs_review`, `failed`. Auto-publish requires `passed` unless the chief editor overrides.
- Critic policies with severity `block` or `must_edit` will prevent publishing and escalate to HITL. Critic results are stored as `critic_result` JSON with detailed messages.

---

## Crawl & Ingest Details (Where the pipeline starts) 🔎

The very beginning of the pipeline is the web crawl and scrape stage — this is where candidate pages are accepted, rejected, or flagged for review.

- Crawler: `agents/crawler/crawler_engine.py` coordinates site-specific strategies (`ultra_fast`, `ai_enhanced`, `generic`) and optionally delegates to `crawl4ai` crawlers. `GenericSiteCrawler` fetches homepages, extracts article links with `_extract_article_links()`, fetches article HTML and runs `_build_article()`.
- Extraction & heuristics: `agents/crawler/extraction.py` runs a multi-tier extraction (Trafilatura -> Readability -> jusText -> plain-css driven fallback). It computes `word_count` and `boilerplate_ratio` (text-to-HTML ratio) and sets `needs_review` when thresholds are not met. The environment flags `ARTICLE_MIN_WORDS` and `ARTICLE_MIN_TEXT_HTML_RATIO` are used to tune this behaviour.
- Paywalls & skip policy: A `PaywallDetector` can mark `paywall_flag` and `skip_ingest`. The crawler records paywall statistics and may trigger `record_paywall_detection()` if dominated by paywalled content. Paywalled pages are not ingested by default.
- HITL & review flow: Pre-ingestion candidates that are borderline can be submitted to the HITL queue via `_submit_hitl_candidates()` for editorial review before ingest. This is useful for novel or low-confidence pages.
- Ingestion: `_ingest_articles()` in `CrawlerEngine` calls the `memory` agent's `ingest_article` tool (`POST /ingest_article` in `agents/memory/main.py`). The memory agent handles upserts into the `sources` table and finalizes `articles` insertion; it also sets `ingestion_status` as `new`, `duplicate`, or `error` and includes `extraction_metadata` for downstream analysers.

These early decisions - whether a page is valid, paywalled, or a candidate for review - strongly influence which articles become available for downstream clustering, analysis, fact-check, and ultimately synthesis.

---

## Job Store & Async APIs

- `POST /api/v1/articles/synthesize` (async) returns a job_id.
- `GET /api/v1/articles/synthesize/{job_id}` polls the job state and returns preview + `critic_result`.
- Job store: `agents/synthesizer/job_store.py` supports in-memory or DB persistence. Default for production: DB-based table migration 006.

---

## Tests & CI

- Unit tests: policy tests of `Analyst`, claim extraction, reasoner, and synthesizer primitives.
- Integration tests (integration marker): Analyst + Fact-Checker + Reasoning + Synthesis + Critic with LLM/Chroma mocked.
- E2E gating tests: ensure admin toggles block or allow publish appropriately, with simulated `chief_editor` approvals.
- CI: add an `integration` runner that executes integration tests in a separate workflow (optionally on a runner with MariaDB + Chroma).

---

## Scripts

- `scripts/synthesize_cluster.py`: local debug wrapper for `POST /synthesize_and_publish`.
- `scripts/fact_check_cluster.py`: debug fact-check for cluster articles.
- `scripts/reason_cluster.py`: preview the `reasoning_plan` for a cluster.
- `scripts/ops/apply_synthesis_migration.sh`: audited apply for DB migrations 004–006.

---

## Observability & Metrics

- Log: `synthesis_job_id`, `cluster_id`, `draft_id`, `model_version`, `start`/`end` times, `critic_result`, `fact_check_status`, `published`boolean.
- Metrics: `synthesis_jobs_started`, `synthesis_jobs_published`, `analysis_latency`, `reasoning_latency`, `fact_check_pass_rate`.
- Use Prometheus and Grafana dashboards to monitor the above metrics.

---

## Deployment, Rollout & Safety

- Disable auto-publish by default for new categories. Clear feature toggles enable limited production rollout with Chief Editor review enforced.
- Start with an internal-only rollout for a narrow category; after validation, expand to canary and full production.
- Make sure the Evidence Audit service is accessible in production; otherwise, any fact-check downstream errors should default to `needs_review`.

---

## Acceptance Criteria

- Unit and integration tests pass.
- Drafts are persisted with full traceability and saved into the selected persistence strategy.
- Admin toggles in Dashboard appear and `GET /admin/get_publishing_config` returns correct values.
- `POST /synthesize_and_publish` uses `min_fact_check_percent_for_synthesis` preflight gating and respects `require_draft_fact_check_pass_for_publish`.
- The job store persists job state when DB option is selected and recovers job status after restarts.

---

## Next steps

- Harden admin endpoints with authentication and auditing.
- Add Chief Editor UI hooks for full HITL publishing.
- Run full E2E tests on an integration runner using MariaDB and Chroma.

---

## References
- `docs/feat_article_creation.md` — per-feature reference
- `agents/synthesizer` — synthesizer code & job store
- `agents/analyst` — claim extraction & fact-check integration
- `database/migrations/004* / 005* / 006*` — schema migrations


End of document.
