# Feature: Article Creation Workflow (feat/article_creation)

## Summary

This document defines the workflow, implementation plan, and acceptance criteria for the `feat/article_creation` branch. The goal is to implement a robust pipeline that synthesizes unbiased, traceable articles from clustered articles, runs the result through a Critic and Fact-checker, optionally performs HITL review, and publishes approved articles to the JustNews website.

We aim to implement an MVP with safe defaults and meaningful tests, followed by incremental improvements and additional integrations.

---

## Scope (MVP)

- Input: cluster of articles (list of article IDs or a cluster ID) produced by existing clustering logic.
- Output: a new synthesized article persisted in MariaDB and Chroma, with full metadata and traceability.
- Integrations: Critic agent, Fact-checker (MANDATORY), Chief Editor review, Reasoning & Analyst agents. External LLMs can be mocked in tests.
- Feature flags to prevent automatic publishing in production by default.

Out of scope (for this branch): full HITL UX polishing, advanced retraining integrations, or complex multi-agent coordination beyond the basic flow.

---

## Design & High-Level Flow

1. (Trigger) A `SYNTHESIZE_CLUSTER` job is created (API, scheduled job, or agent event).
2. `ClusterFetcher` queries Chroma and MariaDB to collect and deduplicate the articles for the cluster.
3. `Analyst` agent analyzes the fetched articles and the cluster for language, sentiment, bias, entity extraction, and other scoring metadata used to influence synthesis and for traceability.
4. Per-article Fact-check (MANDATORY): For each article in the cluster, run a per-article fact-check to validate claims, collect evidence, and store a `source_fact_check` result. These results are stored in `source_fact_checks` and are used to influence further planning.
5. `Reasoning` agent builds a `reasoning_plan` from the `AnalysisReport` and `source_fact_checks`. The plan prioritizes sources/claims, proposes a structure and sections for inclusion, and identifies excluded or flagged content.
6. `SynthesisService` synthesizes a draft article using a model/prompt template and the `reasoning_plan`, and returns a structured `DraftArticle` object containing: `title`, `body`, `summary`, `quotes`, `source_ids`, `trace`, and an `analysis_summary`.
7. Save draft to MariaDB (or `synthesized_articles` table); generate embedding and store in Chroma.
8. Send draft to `Critic` agent for assertions and policy checks; capture `critic_result`.
9. Post-synthesis Draft Fact-check (MANDATORY): Run the fact-checker against the synthesized draft to validate any newly generated claims or paraphrased claims. Capture a `draft_fact_check_status` and `draft_fact_check_trace` for the synthesized content. Draft-level `failed` blocks publishing; `needs_review` requires HITL.
10. If the Critic or draft-level FactChecker returns `failed` or a `needs_review` result, escalate to HITL or mark `needs_revision` and update metadata. No auto-publish on `failed`.
11. When the draft passes Critic and draft FactChecker and `CHIEF_EDITOR_REVIEW_REQUIRED` is `false`, auto-publish; otherwise enqueue for Chief Editor review in the `chief_editor` agent workflow.
12. On publishing: set `is_published=true`, record `published_at` and `published_by`, and update Chroma and the content hosting index.


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
- `fact_check_trace` JSON or TEXT: structured claim-level evidence entries: [{claim, verdict, evidence: [{url, snippet, confidence}], timestamp}]
- `is_published` BOOLEAN DEFAULT FALSE
- `published_at` DATETIME NULLABLE
- `created_by` VARCHAR: `agent:synthesizer` or `user:...`

Analyst-related fields (article-level and cluster-level)
- `analysis_language` VARCHAR
- `analysis_confidence` FLOAT
- `analysis_sentiment` JSON (e.g., polarity, strengths)
- `analysis_bias_score` FLOAT
- `analysis_entities` JSON: [{type, text, links}] for core entity extraction
- `analysis_keywords` JSON
- `analysis_summary` TEXT (clean summary of the analysis useful for human editors and for the SynthesisService to use)
 - `source_fact_checks` JSON: list per ingested article of {article_id, fact_check_status, fact_check_trace, primary_claims} for auditing provenance
 - `cluster_fact_check_summary` JSON: aggregated cluster-level fact check metrics (e.g. percent_verified_sources, flagged_sources_count)
 - `reasoning_plan` JSON: generated by Reasoning agent, including prioritized source list, outline, and claim prioritization
 - `reasoning_version` VARCHAR
 - `reasoning_score` FLOAT

Migrations (deferred):
- DO NOT implement database migrations or persistent schema changes until we have finalized the agent outputs.
- The schema fields listed above are provisional and illustrative. They will be finalized after the `Analyst`, `Fact-Checker`, and `Reasoning` agents are implemented and their precise output formats are defined.
- Once agent outputs are finalized, add migration scripts under `database/core/migrations/` that are idempotent, reversible, and support safe deployment strategies.

Model Class Changes:
- Update `Article` (or add a `SynthesizedArticle` subclass) in `database/models/migrated_models.py` to serialize new metadata fields, and tests for to/from conversions.

Chroma Data: store `is_synthesized` flag in metadata for the vector to simplify discovery.

---

## Synthesis Service: Implementation Details

File/Module: `agents/synthesizer/service.py` (or under `agents/journalist/synthesizer.py`)

Responsibilities:
- Accept event payload { cluster_id | article_ids, options }
- Call `ClusterFetcher` to collect article content and metadata
- Call `Analyst` to get per-article and cluster-level analysis summaries used to guide the prompt and synthesis strategy
 - Call `Reasoning` to obtain a `reasoning_plan` which determines the draft structure, prioritized sources, and excluded content
- Build prompt using defined templates (templates stored in repo or DB; ensure version/ID captured)
- Call the configured synthesis model or use a fallback deterministic method in tests
- Return `DraftArticle` with trace and source IDs
- `DraftArticle` must include an `analysis_summary` derived from Analyst output, showing aggregated language/sentiment/bias scores and entity counts used to bias prompt and mark sections for fact-checking.
 - `DraftArticle` should include a `reasoning_plan_id` or `reasoning_plan` snippet indicating why certain sources were included or excluded, and summaries of prioritized claims.
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

## Analyst Agent: Implementation Details

File/Module: `agents/analyst/service.py` (or `agents/journalist/analyst.py`)

Responsibilities:
- Accept event payloads `{ article_ids | cluster_id | options }` and fetch the relevant content via `ClusterFetcher`.
- Produce per-article and cluster-level analysis including:
  - `language` and `language_confidence`
  - `sentiment` (polarity / scores)
  - `bias_score` (quantitative de-bias metrics)
  - `entities` and `entity_types` (extracted named entities with confidence)
  - `keywords` / `topics`
  - `extraction_confidence` and `source_quality` score
- Return an `AnalysisReport` object with aggregate metrics and per-article details.

Integrations & Use:
- The `SynthesisService` consumes `AnalysisReport` to select voice, adjust prompts, and flag sections for deeper fact-checking.
 - The `SynthesisService` consumes `AnalysisReport` to select voice, adjust prompts, and flag sections for deeper fact-checking. It must take into account the per-article `source_fact_checks` and exclude or de-prioritize articles that have `fact_check_status=failed` or have low evidence confidence.
- The `Critic` uses `AnalysisReport` entities and low-confidence statements to prioritize checks.
- The `FactChecker` can use the extracted entity list to seed verification (e.g., claims involving person/place/time).

Testing:
- Unit tests for parsing, entity extraction, sentiment/bias scoring, language detection and confidence thresholds.
- Integration tests to assert Analyst output shape and that it is used by the SynthesisService in draft generation.

Prompts & Config:
- Support multiple analysis engines and fallback (e.g. langdetect, open-source sentiment tools, and named-entity recognition models) configured via `ANALYST_BACKEND`.
- Config flags like `ANALYST_MIN_CONFIDENCE` and `ANALYST_SCORE_WEIGHTS` should be available to tune scoring.

---

## Reasoning Agent: Implementation Details

File/Module: `agents/reasoning/service.py` (or `agents/journalist/reasoning.py`)

Responsibilities:
- Accept an `AnalysisReport` plus `source_fact_checks` and return a `reasoning_plan` object that includes:
  - Prioritized sources (ordered list of article IDs with reasons and evidence)
  - Sections and structure for the synthesized article (outline)
  - Key claims to include, with source references and confidence score
  - Items to exclude (and why, e.g., low confidence or contradictory sources)
  - Any rebuttal or cross-check tasks requested from the Fact-Checker
- Provide a concise `reasoning_score` to indicate confidence in the plan and a `reasoning_version` identifier for traceability.

Integrations & Use:
- The `SynthesisService` consumes `reasoning_plan` to guide prompt construction and ensure alignment to the prioritized structure.
- The `FactChecker` and `Critic` can use the `reasoning_plan` to focus checks on high-priority claims or flagged sources.
- The Chief Editor can view the `reasoning_plan` to understand source selection and to inform review decisions.

Testing:
- Unit tests for the reasoning plan generation, including edge cases where sources disagree.
- Integration tests to validate the end-to-end path Analyst -> Fact-Checker -> Reasoning -> Synthesis.

Prompts & Config:
- Allow for `REASONING_STRATEGY` flags such as `majority`, `weighted_trust_based`, `timeline_prioritized`, or `no_primary_source` to be configurable per scenario.

Acceptance criteria for Reasoning:
- The `reasoning_plan` is auditable and must include reasons explaining why sources were chosen or excluded.
- Reasoning must respect configured thresholds (e.g., exclude sources with `fact_check_status=failed`).



---

## Critic & Fact-Check Integration

- There are two Fact-Check phases:
  - Pre-reasoning: Per-article fact-checks (MANDATORY) — run against each ingested article to produce `source_fact_checks` used by Reasoning.
  - Post-synthesis: Draft-level fact-checks (MANDATORY) — run against the synthesized draft to validate any newly generated or paraphrased claims.

- After the draft is generated, call the `Critic` agent: `agent/critic` or module call: `agents/critic/validate()`.
- Capture `critic_result` JSON including issues, categories, severity.
- If Critic indicates `block` severity, set `status=needs_revision` and optionally escalate to HITL.
## Fact-Checker: Implementation & Challenges (MANDATORY)

Fact-checking is mandatory and is the most critical and technically challenging component in this workflow. The fact-checker validates claims in the synthesized draft and verifies any content that would materially affect the reader’s understanding. This component must be robust, auditable, and tuned for a low false-positive rate while prioritizing safety and correctness.

Responsibilities:
- Accept an `AnalysisReport` and `DraftArticle` as inputs.
- Extract claims from the text using the Analyst's entity & claim detection metadata.
- For each claim, perform verification steps including: cross-referencing trusted sources, knowledgebase queries, supporting evidence collection, timestamped provenance logging, and confidence scoring.
- Summarize results into an actionable `fact_check_status` for the draft: `pending`, `passed`, `failed`, `needs_review`.
- Produce a `fact_check_trace` detailing the sources checked and evidence IDs for auditability.
- Provide an API for manual and automated review: `POST /api/v1/articles/:id/fact_check` to force re-checks or revalidate upon new evidence.

Behavior & failure modes:
- The fact-checker must never be optional for publishing paths: if the system cannot perform a fact check because of environmental failures (downstream API unreachable, missing resources, etc.), the draft must default to `needs_review` and not auto-publish.
- For low-confidence checks, the fact-checker returns `needs_review` and attaches suggested remedial actions that the Chief Editor or HITL reviewer should consider.
- For high-confidence failures (claims contradicted by multiple independent sources or internally contradictory statements), the fact-checker returns `failed` which should automatically block publishing until addressed.

Implementation considerations & complexity:
- Claim extraction and classification is non-trivial; the Analyst agent must provide high-quality candidate claims and entity tags so the fact-checker can prioritize.
- The fact-checker will likely combine multiple resources: curated internal knowledge graphs, external fact-checking APIs, newswire datasets, and trusted data sources. Establishing reliable sources and maintaining coverage across topics is a long-term effort.
 - The fact-checker will likely combine multiple resources: curated internal knowledge graphs, external fact-checking APIs, newswire datasets, and trusted data sources. Establishing reliable sources and maintaining coverage across topics is a long-term effort.
 - The fact-checker must evaluate and return per-source verdicts to allow full traceability for the final synthesized article: for each article in the input cluster a `source_fact_check` record must be produced and stored.
- For scalable verification, introduce caching of evidence and results (with TTL), dedup of requests, and batch verification of claims for cluster-level efficiency.
- Rely on robust identity/resource handling to minimize false matches (canonicalize entity names and references).
- Evaluate trade-offs between speed and depth of verification; the initial MVP can use faster, conservative checks to avoid publishing incorrect items.

Testing and QA:
- Build a `fact_check_test_dataset` with labelled claims and known verdicts to validate algorithm accuracy and to evaluate false-positive/false-negative rates.
- Add unit tests for claim extraction and matching logic.
- Add integration-level tests that simulate untrusted and trusted evidence sources and confirm correct `fact_check_status` aggregation.
 - Add integration-level tests that simulate untrusted and trusted evidence sources and confirm correct `fact_check_status` aggregation AND per-article `source_fact_checks` are produced and included in the `AnalysisReport`.
- Add continuous evaluation via a validation harness that tests the system with real-world examples before enabling auto-publish for an article category.

Acceptance criteria for Fact-checker:
- The system should not auto-publish an article unless Fact-checker returns `passed` or `passed-with-notes` where Chief Editor overrides allowed.
- Fact-check `failed` should populate `fact_check_trace` and block publishing automatically.
 - All cluster input articles must produce a `source_fact_check` entry. The final draft must include references to the verified source IDs and their fact-check verdicts.
 - If a cluster has a high percentage of `source_fact_check` failures above a configured threshold (e.g., 50%), the SynthesisService should automatically abort synthesis and require human intervention.
- Audit logs must be stored with claim-level provenance and source evidence identifiers.
- Baseline accuracy thresholds (to be determined by the project): e.g., >80% precision on verified claims for a given category is a desirable target for MVP; but the initial rollout must use a conservative default.

Integration & rollout policy:
- Start with a conservative MVP that runs checks against a small set of curated trusted reference sources or an external fact-check service (if available) and defaults to `needs_review` on uncertain items.
- Improve coverage iteratively by adding more sources, offline-scraped knowledge graphs, and canonicalization logic.
- Prioritize high-risk claim categories (public figures, numbers, legal/medical statements) in early rollout phases.

 - Use analyst-generated entity metadata and detected claims to seed fact-checking (e.g., verify entity-based claims or flagged low-confidence statements)

---

## Chief Editor / HITL Workflow

- If `CHIEF_EDITOR_REVIEW_REQUIRED=1`, the system should place the draft in a Chief Editor review queue with a reference to `id` and metadata.
- Chief Editor should be able to edit the draft and accept/reject/publish. This requires frontend hooks and endpoints.
- Provide `GET /api/v1/articles/drafts` and `POST /api/v1/articles/:id/publish` for Chief Editor actions.

---

## API Endpoints & Scripts

- POST `/api/v1/articles/synthesize` { cluster_id | article_ids, options } -> returns a job_id / draft.
 - POST `/api/v1/articles/analyze` { article_ids | cluster_id } -> returns analysis results for articles & cluster
 - POST `/api/v1/articles/fact_check` { article_ids | cluster_id } -> runs fact-check for each article and returns `source_fact_checks` and `cluster_fact_check_summary`
 - POST `/api/v1/articles/reason` { article_ids | cluster_id } -> produces a `reasoning_plan` and returns a `reasoning_plan_id` and summarized plan
 - GET `/api/v1/articles/:id/reasoning` -> retrieve reasoning plan for article/cluster
 - GET `/api/v1/articles/:id/analysis` -> returns analysis metadata for a single article
- GET `/api/v1/articles/synthesize/{job_id}` -> job status + preview + critic_result
- GET `/api/v1/articles/:id/draft` -> retrieve a draft article
- POST `/api/v1/articles/:id/publish` -> publish (Chief Editor or automated if gate allows)

Script for debugging:
- `scripts/synthesize_cluster.py` should exist to exercise the service locally and return the draft
 - `scripts/analyze_cluster.py` should exist to exercise `Analyst` locally and preview analysis results
 - `scripts/fact_check_article.py` should exist to run fact-checks locally against a sample dataset and to debug evidence collection
 - `scripts/fact_check_cluster.py` should exist to exercise fact-checks for each article in a cluster and produce a cluster summary with per-article `source_fact_checks`
 - `scripts/reason_cluster.py` should exist to run the reasoning agent on a cluster and preview the `reasoning_plan` results

---

## Test Strategy

- Unit Tests:
  - `tests/agents/synthesizer/test_synthesis_service.py`: verify shaping of draft
  - `tests/database/test_synthesized_article_model.py`: model serialization
  - `tests/database/test_chromadb_utils` integration points using mocks

- Integration Tests:
  - `tests/integration/test_article_creation_flow.py` marked with `integration` marker: a simulated run from cluster -> draft -> critic -> saved; requires integration fixtures.
 - `tests/agents/analyst/test_analyst_service.py`: verify entity parsing, bias scoring and confidence handling;
 - Add an integration path: `tests/integration/test_analysis_synthesis_flow.py` that demonstrates Analyst + SynthesisService usage with mocked LLM & Chroma.
 - `tests/agents/fact_checker/test_fact_checker_per_article.py`: verify per-article claims are extracted, verified, and produce `source_fact_checks` entries and a cluster summary.
 - `tests/agents/reasoning/test_reasoning_service.py`: validate reasoning plan generation and that it excludes low-confidence sources and highlights key claims and structure
 - Add an integration path: `tests/integration/test_analysis_reasoning_synthesis_flow.py` that demonstrates Analyst + FactChecker + Reasoning + SynthesisService usage with mocked LLM & Chroma.

- Performance Tests (later):
  - `tests/database/test_dual_database_performance.py` style tests for large cluster sizes

---

## CI & Preflight

- Add unit tests to run as part of existing CI suite
- Add an `integration` marked job in `.github/workflows/pytest.yml` that runs the integration workflows in a dedicated runner
- Feature flags: use `SKIP_PREFLIGHT` and `ARTICLE_SYNTHESIS_ENABLED` controls for dev vs CI
- Fact-checker integration tests should be required in CI for main PRs and a staged `pre-prod` run is recommended before auto-publish is permitted in production.

---

## Observability & Metrics

- Log events: `synthesis_job_id`, `cluster_id`, model/version used, start/end times, `critic_result`, `fact_check_status`, `published` status
- Metrics:
  - `synthesis_jobs_started` (counter)
  - `synthesis_jobs_failed` (counter)
  - `synthesis_jobs_published` (counter)
  - Traces for model latency (gauge)
    - `analysis_jobs_started` (counter)
    - `analysis_jobs_failed` (counter)
    - `analysis_latency` (gauge)
    - `analysis_bias_score_distribution` (histogram)
    - `reasoning_jobs_started` (counter)
    - `reasoning_jobs_failed` (counter)
    - `reasoning_latency` (gauge)
    - `reasoning_plan_quality` (histogram)

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

- Define agent outputs and finalize schema (Analyst, Fact-Checker, Reasoning) — DO NOT implement DB migrations until outputs are finalized.
- Implement `ClusterFetcher`
- Implement `Analyst` agent skeleton & unit tests
- Implement per-article Fact-Checker (MVP stub) and `scripts/fact_check_cluster.py`
- Implement `Reasoning` agent skeleton & unit tests
- Implement `SynthesisService` skeleton with a deterministic test stub and `scripts/synthesize_cluster.py`
- Add Critic integration & finish Fact-Checker integration
- Add API endpoints for analyze/fact_check/reason/reasoning results and `synthesize` endpoints
- Add Chief Editor review and publish endpoints (backend only for MVP)
- Add unit tests and a basic integration test for Analysis -> Reasoning -> FactChecker -> Synthesis -> Critic -> Draft Fact-Check -> Publish
- Add observability metrics and feature flags

---

## Owner & Timeline

- Owner: `agents/journalist`, `agents/synthesizer`, and `database` owners together
 - Owner: `agents/journalist`, `agents/synthesizer`, `agents/fact_checker`, and `database` owners together
 - Owner: `agents/journalist`, `agents/synthesizer`, `agents/reasoning`, `agents/fact_checker`, and `database` owners together
- Timeline: break down into 2-week sprints:
  - Sprint 1: Data model + SynthesisService + ClusterFetcher + Unit tests
  - Sprint 2: Critic & Fact-check integration + API endpoints + Integration tests
  - Sprint 2.5: Fact-Checker dataset & API expansion (dedicated data & backend sprint)
  - Sprint 2.75: Reasoning agent integration (algorithm & pilot rollout)
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
