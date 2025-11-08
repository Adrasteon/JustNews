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

### Progress update (2025-11-01) — restoration and tests

- Restored summariser: the adaptive summariser `summarise_adaptive_articles` has been restored to the active code path at `agents/crawler/adaptive_metrics.py` (moved from `archive/experimental/raw_html_profile_spur/`). This closes the runtime gap where scheduler and dashboard call sites expected the module to exist.
- Unit tests added: a focused pytest module was added at `tests/agents/crawler/test_adaptive_metrics.py` covering empty/no-adaptive inputs and a basic aggregation case.
- Tests executed: the new test file was executed locally and both tests passed (2 passed, 0 failed). This validates the summariser's basic behaviour and aggregation shapes.

Next immediate steps (short):

- Commit & push: commit the restored module and tests to the `feat/k8s` branch and push to the remote (not yet committed in this workspace snapshot).
- Scheduler dry-run: run a focused scheduler dry-run to confirm `scripts/ops/run_crawl_schedule.py` imports the summariser successfully and that Prometheus textfile + `scheduler` JSON include the adaptive summary fields.
- Dashboard verification: once the scheduler emits the expected state JSON/metrics, validate the dashboard agent `/api/crawl/scheduler` responses and ensure the Grafana panels surface the new fields as intended.

These updates implement the highest-priority fix from the audit (restore the summariser) and prepare us to validate end-to-end telemetry.

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

## Phase 5 – Crawler Resilience Enhancements (COMPLETED)

### Advanced Anti-Detection & Content Access Features
1. **Modal Handling**: Automatic detection and removal of consent overlays, cookie banners, and sign-in modals
   - Synthetic cookie injection for consent management
   - Pre-extraction HTML processing to remove modal interference
   - Configurable consent cookie values and modal detection patterns

2. **Paywall Detection**: Multi-layered paywall analysis and content filtering
   - Heuristic detection based on content patterns and access restrictions
   - Optional MCP-based remote analysis for complex paywall identification
   - Article metadata annotation with confidence scores and skip decisions
   - Configurable detection thresholds and analysis depth

3. **User Agent Rotation**: Intelligent browser fingerprinting management
   - Domain-specific user agent pools for targeted site compatibility
   - Deterministic rotation strategies with configurable pool sizes
   - Fallback mechanisms for unsupported or problematic user agents

4. **Proxy Pool Management**: IP diversity and anti-detection through proxy rotation
   - Round-robin proxy selection with configurable pool management
   - Proxy health monitoring and automatic failure recovery
   - Support for HTTP/HTTPS proxies with authentication

5. **Stealth Headers**: Browser simulation and fingerprinting evasion
   - Configurable header profiles mimicking real browser behavior
   - Accept-Language and Accept-Encoding customization
   - Header injection for requests with stealth factory patterns

### Implementation Architecture
- **Modular Design**: Independent enhancement components in `agents/crawler/enhancements/` package
- **Configuration-Driven**: Full Pydantic schema integration with runtime toggles
- **Optional Features**: All enhancements default to disabled for backward compatibility
- **Engine Integration**: Seamless integration into `CrawlerEngine` and `GenericSiteCrawler`
- **Error Resilience**: Comprehensive exception handling with graceful degradation

### Configuration Schema
```json
{
  "crawling": {
    "enhancements": {
      "enable_user_agent_rotation": false,
      "enable_proxy_pool": false,
      "enable_modal_handler": false,
      "enable_paywall_detector": false,
      "enable_stealth_headers": false,
      "user_agent_pool": [],
      "per_domain_user_agents": {},
      "proxy_pool": [],
      "stealth_profiles": [],
      "consent_cookie": {"name": "justnews_cookie_consent", "value": "1"},
      "paywall_detector": {"enable_remote_analysis": false, "max_remote_chars": 6000}
    }
  }
}
```

### Production Benefits
- **Enterprise-Grade Scraping**: Robust web scraping for complex, protected news sites
- **Anti-Detection Resilience**: Multiple evasion techniques for reliable data collection
- **Content Quality Improvement**: Enhanced article extraction through modal removal and paywall handling
- **Operational Reliability**: Graceful handling of site restrictions and access barriers
- **Future-Proof Architecture**: Modular design supports additional enhancements without disruption

**Status**: **PHASE 5 COMPLETE** - Advanced crawler resilience features fully implemented and production-ready
