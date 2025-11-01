# Crawl & Scrape Stack – Recommended Direction

## 1. Simplify Around Crawl4AI as the Primary Runner
- **Adopt Crawl4AI as the orchestration core.** Wrap our scheduler so every job builds a `BrowserConfig` + `CrawlerRunConfig` (and optional `AdaptiveConfig`) instead of hand-running Playwright helpers. This keeps crawl depth, link policies, and JS interactions declarative, not hard-coded.
- **Retain lightweight fallbacks.** Keep a minimal `requests`-based ping path for health checks or static sites; everything else funnels through `AsyncWebCrawler.arun` / `arun_many` or `AdaptiveCrawler`.
- **Drive behavior from per-site profiles.** Configuration files specify mode (landing, section, deep), link filters, scripts, and extraction strategy—no separate bespoke code per source.

## 2. Keep Trafilatura as the First-Pass Extractor
- **Extraction pipeline stays modular.** Continue passing HTML from Crawl4AI into our Stage B pipeline. Trafilatura remains tier‑1 for text/metadata; readability, jusText, and plain sanitiser remain safety nets.
- **Measure before reinvention.** If Trafilatura success stays high, no need to embed Crawl4AI’s markdown output directly. Where Trafilatura underperforms, we can toggle a profile flag to consume Crawl4AI’s generated markdown or layer an LLM extraction strategy for that site.

## 3. Avoid Over-Engineering Scripts
- **Favor config over code.** Use C4A-Script only when a site needs interaction (login, popups). Store scripts alongside profiles, keep them short, and reuse via `PROC` blocks.
- **Guard dependency sprawl.** Stick to Crawl4AI + existing extractors; avoid bolting on multiple scraping frameworks. Trafilatura/readability/justext already cover extraction fallbacks.
- **Leverage built-in strategies sparingly.** Invoke `RegexExtractionStrategy`, `LLMExtractionStrategy`, or `CosineStrategy` only when a site clearly benefits. Default to our current article body extraction unless proven insufficient.

## 4. Implementation Snapshot (Oct 2025)
- **Scheduler-aware profiles:** `scripts/ops/run_crawl_schedule.py` now accepts `--profiles` (defaults to `config/crawl_profiles.yaml`) and inlines the resolved payload into each crawl job as `profile_overrides`.
- **Profile registry:** `agents/crawler_control/crawl_profiles.py` loads YAML profiles, expands `{domain}` placeholders, and maps `www.`/bare hostnames so operators only touch configuration.
- **Crawler adapter:** `agents/crawler/crawl4ai_adapter.py` translates profile dictionaries into Crawl4AI `BrowserConfig`/`CrawlerRunConfig` objects, follows scored internal links within the declared `max_pages`, and still feeds the Trafilatura pipeline.

### Adaptive crawling & telemetry (Oct–Nov 2025)

- The adapter will now use `AdaptiveCrawler` when a profile provides an `adaptive` block and a `query` hint. Adaptive runs are used to focus crawl effort and can replace full traversal when they return sufficient coverage. Adaptive output is converted back into the existing article shape so downstream agents see the same payloads.
- We emit lightweight adaptive metrics and counters into the Stage B metrics API (e.g. `adaptive_runs_total`, `adaptive_confidence`, `adaptive_articles_emitted`, `adaptive_pages_crawled`). These metrics are intentionally conservative and resilient to missing Prometheus/GPU packages.
- Operational note: because adaptive runs may be short-circuited, operators should inspect `extraction_metadata.crawl4ai.adaptive_run` in stored articles to audit run confidence and stop reasons.
- **Engine fallback:** `CrawlerEngine.run_unified_crawl(...)` applies overrides per domain and falls back to the legacy `GenericSiteCrawler` when Crawl4AI is unavailable or a profile opts out via `engine: generic`.

### Editing profiles
1. Update or add entries under `config/crawl_profiles.yaml`.
2. Run the scheduler in dry-run mode to validate payload expansion:
	```bash
	JUSTNEWS_PYTHON scripts/ops/run_crawl_schedule.py --dry-run --profiles config/crawl_profiles.yaml
	```
3. Deploy profile updates by syncing the YAML to the scheduler host; no Python code changes required.

## 5. Incremental Migration Plan
1. **Prototype wrapper:** ✅ Complete – scheduler/adapter path in place for selected domains.
2. **Profile definitions:** Continue migrating remaining sources into YAML profiles; capture per-cohort defaults (`start_urls`, `link_preview`).
3. **Rollout & metrics:** Expand coverage once metrics confirm parity or improvement. Track extraction success, coverage, and performance to catch regressions early.
4. **Clean-up legacy paths:** Once Crawl4AI covers all production sites, retire unused playwright/browser helpers to reduce maintenance.

## 6. Guiding Principles
- **Simplicity first:** One orchestrator (Crawl4AI), one extraction pipeline (Trafilatura-first), declarative configs for per-site behavior.
- **Flexibility through profiles:** Operators can dial crawl depth, link filters, or scripts without editing Python.
- **Observability baked in:** Continue Stage B metrics, plus log Crawl4AI `CrawlResult` stats to inform profile tuning.

Following this plan keeps the stack manageable, avoids bespoke crawler rewrites, and lets us scale depth or precision per site without accumulating fragile code. Trafilatura remains the extraction workhorse while Crawl4AI handles navigation, link discovery, and controlled expansion. 