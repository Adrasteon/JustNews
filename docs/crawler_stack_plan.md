# Crawler Stack Workplan

## Objectives
- Standardize on Crawl4AI adaptive crawling and precision extraction.
- Retire redundant schema-generation paths and ensure GPU inference is used only when it delivers measurable gains.
- Improve observability, reproducibility, and rollback paths for crawl operations.

## Phase 0 – Cleanup
1. Remove legacy YAML/schema generation scripts and outputs.
2. Pin Crawl4AI and model dependencies in `environment.yml`/`requirements.txt` and document installation prerequisites.
3. Capture a "golden path" for running a single Crawl4AI job (CLI invocation plus agent entrypoint) for onboarding.

## Phase 1 – Crawler Core
1. Wrap Crawl4AI `AdaptiveCrawler` with per-site configuration profiles (confidence thresholds, `min_gain_threshold`, `top_k_links`).
2. Add content filters (e.g., `BM25ContentFilter`, `CosineStrategy`, table scoring) based on site archetypes.
3. Enforce HTML length/size limits before extraction and define retry/fallback policy for fetch failures.
4. Persist raw HTML, Markdown, and structured artifacts with lineage metadata (run id, config, confidence).

### Progress update (2025-11-01)

- AdaptiveCrawler integration: The Crawl4AI adapter now wires `AdaptiveCrawler` runs into the ingestion path when profiles include `adaptive` blocks and a `query` hint. Adaptive outputs are transformed back into our article format and annotated with `extraction_metadata.crawl4ai.adaptive_run` containing confidence, coverage, pages crawled, stop_reason, and source score.
- Metrics: adaptive telemetry (counters/gauges) was added to the Stage B metrics API so operators can monitor adaptive run frequency and quality (names: `adaptive_runs_total`, `adaptive_articles_emitted`, `adaptive_confidence`, `adaptive_pages_crawled`, and `adaptive_coverage_<metric>`).
- Dashboard telemetry: the dashboard agent now exposes `/api/crawl/scheduler`, returning the latest scheduler snapshot (including adaptive summary, derived metrics, and recent history) so the UI can surface confidence trends and stop-reason distributions without scraping raw logs.
- Next actions: finalize E2E validation, hook the dashboard UI panels into the new scheduler endpoint, and schedule batched re-runs for domains that previously failed or returned low confidence.

## Phase 2 – Crawler Control
1. Define a crawl job spec (start URL, query, site profile, priority) and integrate with the existing balancer/orchestrator.
2. Track adaptive metrics (confidence, pages crawled, stop reason) in the metrics store.
3. Emit alerts or automatic escalations when confidence falls below target or saturation is not achieved within budget.

## Phase 3 – Scout Integration
1. Extend the scout agent to request crawl jobs through the control plane and consume canonicalized outputs.
2. Trigger multi-model validation only for high-priority stories or low-confidence crawls.
3. Cache recent crawl summaries for downstream analyst/fact-checker agents.

## Phase 4 – Observability & QA
1. Build a regression suite comparing legacy outputs to Crawl4AI across representative domains.
2. Add tracing spans/instrumentation around crawl stages and dashboard summaries (throughput, failures, confidence trends).
3. Schedule periodic reviews to tune profiles and validate coverage/quality metrics.

## Future Enhancements
- Implement domain-specific custom filters if needed (e.g., finance, politics, sports).
- Introduce conditional multi-model reconciliation when adaptive confidence < 0.75.
- Expand dashboards with automation for rollback recommendations when crawl quality regresses.
