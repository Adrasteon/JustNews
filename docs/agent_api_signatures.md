# Agent API Signatures and Payload Contracts

This file summarizes key API endpoints, MCP call signatures, and payload shapes used across agents. Use this as a reference when implementing tests, forwarders, or new integrations.

1) HITL Service (HTTP API)
- `POST /candidates`
  - Body (JSON):
    - `id`: string (candidate id)
    - `url`: string
    - `site_id`: string
    - `title`: string
    - `extracted_text`: string
    - `extraction_metadata`: object
    - `publish_time`: iso8601 string (optional)
  - Response: `{ "candidate_id": "..." }`

- `POST /labels`
  - Body: `{ "candidate_id": "...", "label": "accept|reject|review", "user": "...", "comment": "..." }`
  - Response: `{ "label_id": "...", "ingestion_status": "pending" }`

2) MCP Bus calls (agent-to-agent RPC)
- `memory.ingest_article`
  - Payload (JSON):
    - `site_id` (str), `url` (str), `title` (str), `cleaned_text` (str),
    - `extraction_metadata` (dict), `source_html_path` (str, optional),
    - `ingest_meta` (dict: `run_id`, `source`, `submitted_by`)
  - Return: `{ "article_id": <int|string>, "status": "ok" }`

3) Crawl4AI adapter expectations
- `crawl_site_with_crawl4ai(site_config, profile, max_articles)` returns `list[dict]` where each dict contains:
  - `url`, `cleaned_html` / `markdown` or `html`, `metadata`, `links` (internal/external), `score`

4) Archive / Storage agent
- `archive.store_article`
  - Payload: `{ "article_id": ..., "raw_html_path": "/path/to/file", "archive_meta": {...} }`

Notes on versioning and backward compatibility
- Keep payloads additive. New fields should be optional; consumers should fallback gracefully when fields missing.
- Use `site_id` as string across all payloads to avoid schema mismatch.
