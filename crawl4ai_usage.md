# Crawl4AI Usage Overview

## Core Python API
- `AsyncWebCrawler.arun(url, config=None, session_id=None, **kwargs) -> CrawlResult`: primary async crawl call. Accepts `CrawlerRunConfig`, optional session identifier, and returns a rich `CrawlResult` (markdown, fit HTML, metadata, media, links, network logs).
- `AsyncWebCrawler.arun_many(urls, config=None, dispatcher=None, …) -> list[CrawlResult] | AsyncGenerator`: batch/streaming crawl over multiple URLs. Supports a shared config or per-URL configs and concurrency dispatchers (e.g., `MemoryAdaptiveDispatcher`).
- `CrawlerRunConfig`: runtime behavior toggle (C4A script, markdown generator, link preview scoring, screenshot capture, cache mode, etc.).
- `BrowserConfig`: Playwright/browser session parameters (headless mode, device profiles, timeouts, download directories) embedded in API/CLI payloads.
- `AdaptiveCrawler` + `AdaptiveConfig`: iterative crawl orchestrator with coverage scoring. `digest(start_url, query, …)` follows links while `confidence_threshold`, `max_pages`, `top_k_links`, and `min_gain_threshold` constraints hold.
- `SeedingConfig`: upfront URL discovery (sitemap source, include patterns, BM25 query scoring, score thresholds, limits) for feeding `arun_many`.
- `LinkPreviewConfig`: attaches to `CrawlerRunConfig`; scores/filters internal/external links with pattern filters, query, score thresholds, preview metadata.
- `DefaultMarkdownGenerator` + `LLMContentFilter`: transforms cleaned HTML into markdown; LLM filter (provider string, instruction, token limits) keeps desired sections.
- `CrawlResult` helpers: access `links['internal'|'external']`, `media`, `network_requests`, `downloads` for downstream analytics.

## Extraction Strategies
- `RegexExtractionStrategy`: uses built-ins for emails/URLs, custom regex dicts, or `generate_pattern()` via LLM (cached JSON for reuse).
- `JsonCssExtractionStrategy` / `JsonXPathExtractionStrategy`: schema-driven selector extraction for structured pages.
- `LLMExtractionStrategy`: schema- or block-based extraction with configurable LLM (`provider`, `api_token`, custom `instruction`, optional Pydantic schema, chunking controls, `base_url`, `extra_args`).
- `CosineStrategy`: semantic similarity selector (`semantic_filter`, `word_count_threshold`, `sim_threshold`, `max_dist`) to group relevant sections.
- PDF stack: `PDFCrawlerStrategy` + `PDFContentScrapingStrategy(extract_images, save_images_locally, image_save_dir, batch_size)` produce markdown plus media metadata.
- Chunking utilities:
  - `OverlappingWindowChunking(window_size, overlap)` for sliding windows.
  - `RegexChunking(patterns)` for regex-based segmentation.
  - `TopicSegmentationChunking` (TextTiling) for topic-aware splits.
  - Chunk parameters also live on `LLMExtractionStrategy` (`chunk_token_threshold`, `overlap_rate`, `word_token_rate`, `apply_chunking`).
- LLM schema helpers: define Pydantic models (e.g., `ResearchInsights`) and feed `.model_json_schema()` to `LLMExtractionStrategy`.

## C4A-Script Automation Primitives
- Navigation: `GO <path>`, `WAIT <selector> <seconds>`, `CLICK <selector>`, `PRESS <key>`.
- Input: `TYPE "literal"`, `TYPE $variable` after `SETVAR name = "value"`.
- Control flow: `IF (EXISTS <selector>) THEN <command>`, `PROC … ENDPROC` for reusable blocks, call by procedure name.
- Scripting: `EVAL `<javascript>` for arbitrary DOM/JS actions; `#` comments ignored at runtime.
- Best practices: wait before interactions, guard optional elements, encapsulate repeated sequences in `PROC`.

## REST & Service Endpoints
- Core crawl:
  - `POST /crawl` (sync), `/crawl/stream` (streaming), `/crawl/job` → `/crawl/job/{id}` (async jobs).
- Specialized outputs:
  - `/html` (fit HTML), `/md` (markdown with filters), `/screenshot`, `/pdf`, `/execute_js`.
- LLM & config utilities:
  - `/llm/{url}` (Q&A over page), `/ask` (library context search), `/config/dump` (validate Python config snippets).
- Observability & docs:
  - `/health`, `/metrics`, `/schema`, `/playground`.
- MCP integrations: `/mcp/sse`, `/mcp/ws`, `/mcp/schema` for Model Context Protocol clients.
- Payloads carry serialized `BrowserConfig`/`CrawlerRunConfig` objects (`{"type": "…", "params": {...}}`) and can override providers (`"provider": "groq/mixtral-8x7b"`).

## CLI & Tooling
- `crwl config list`: dump global configuration values/defaults/descriptions.
- `crwl examples`: list CLI usage samples.
- `crawl4ai-setup`, `crawl4ai-doctor`: install Playwright browsers and run diagnostics.
- Attribution helpers: badges, plain text, BibTeX for documentation.

## Command Samples
- Inspect available CLI defaults quickly:
  ```bash
  crwl config list | head
  ```
- Dry-run the Stage B scheduler against the finance cohort while loading explicit profile overrides:
  ```bash
  CRAWL_PROFILE_PATH=config/crawl_profiles.yaml python scripts/ops/run_crawl_schedule.py \
    --dry-run \
    --testrun \
    --profiles config/crawl_profiles.yaml \
    --schedule config/crawl_schedule.yaml
  ```
- Trigger a background crawl job directly against the agent API with a profile override for `markets.example.com`:
  ```bash
  curl -X POST http://127.0.0.1:8015/unified_production_crawl \
    -H 'Content-Type: application/json' \
    -d '{
      "args": [["markets.example.com"]],
      "kwargs": {
        "max_articles_per_site": 8,
        "concurrent_sites": 1,
        "profile_overrides": {
          "markets.example.com": {"profile_slug": "finance-default"}
        }
      }
    }'
  ```
- Launch the crawler agent with live reloading during local development:
  ```bash
  uvicorn agents.crawler.main:app --host 0.0.0.0 --port 8015 --reload
  ```

## Output Structures & Metrics
- `CrawlResult` fields: `url`, `success`, `markdown` (raw/fit), `links`, `metadata` (status code, content type), `media` (images/video with relevance), `network_requests`, `downloads`, `error_message`.
- `AdaptiveCrawler.get_relevant_content(top_k)` returns knowledge base slices (`url`, `content`, `score`, metadata).
- Coverage scoring: aggregate term coverage via IDF-weighted formulas to measure query saturation.

## Usage Patterns
1. Discover candidate URLs with `SeedingConfig`.
2. Crawl via `AsyncWebCrawler.arun/arun_many`, optionally wrap in `AdaptiveCrawler` for deeper coverage.
3. Attach extraction strategy (regex, schema, LLM, cosine) or markdown filter to shape output.
4. Use chunking strategies for long-form content before LLM-based extraction.
5. Combine PDF or JS automation (C4A-script, `execute_js`) for non-HTML sources.
6. Integrate with services through REST endpoints, streaming responses, or embed C4A scripts for deterministic DOM workflows.

## Internal Integration (JustNews)
- Scheduler submits crawl runs with per-domain overrides from `config/crawl_profiles.yaml`; the path is configurable via `--profiles` or the `CRAWL_PROFILE_PATH` environment variable.
- `agents/crawler_control/crawl_profiles.py` normalises hostnames and expands `{domain}` tokens before handing payloads to the crawler agent.
- `agents/crawler/crawl4ai_adapter.py` instantiates `BrowserConfig` and `CrawlerRunConfig` based on those payloads, follows scored internal links when requested, and feeds cleaned HTML back into the Trafilatura-first extraction pipeline.
