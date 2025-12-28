## JustNews Live-run E2E Plan

This document contains the staged plan to get JustNews working end-to-end — from crawl -> ingestion -> parsing ->
editorial -> publish — with measurable checks and debugging guidance. This file is generated from an actionable plan and
mirrors the roadmap for the `dev/live-run-tests` branch.

High-level goals:

- Crawl agents fetch URLs and reliably store raw HTML

- Ingest and normalize raw HTML into records

- Parse structure and extract necessary fields

- Agents (journalist, fact_checker, synthesizer) produce a draft with checks

- Publish a final article and verify accessible content

- Observe and measure the success/failure of each stage with dashboards and counters

## Status snapshot — 4 Dec 2025

| Stage | Status | Evidence | Gaps | | --- | --- | --- | --- | | 0. Setup & baseline | ✅ Complete | `docs/dev-setup.md`,
`tests/smoke/test_stage0_env.py`,`scripts/dev/canary_urls.txt`,`infrastructure/systemd/scripts/enable_all.sh` | Keep
env drift checks automated in CI | | 1. Crawl & fetch | 🟡 Partially complete | Crawl4AI scheduler + profiles
(`scripts/ops/run_crawl_schedule.py`,`config/crawl_profiles/`), Stage B metrics counters, crawler→HITL verified in
`article_proc_path.md`. Dashboard now queries sources directly from the database
(`agents/dashboard/dashboard_engine.py`) and`agents/dashboard/config.json` filters have been relaxed to avoid excluding
sources by default. | Automatic verification that raw HTML lands in archive storage and success dashboards | |

1. Ingestion & normalization | 🟡 Archive → Stage B wired |
`archive.queue_article`MCP tool + raw HTML snapshot metrics (`tests/agents/test_archive_ingest_pipeline.py`,
`tests/agents/test_archive_raw_html_snapshot.py`) | Need Grafana wiring for new ingest/raw_html counters + automated DB
visibility gates | | 3. Parsing & structure extraction | 🟡 Fixtures in CI | Stage B pipeline still Trafilatura- first
per `crawl_and_scrape_stack.md`, deterministic checks now live in`tests/parsing/test_canary_articles.py` with
`tests/fixtures/canary_articles/` | Need broader fixture coverage (authors/dates edge cases) and linkage to normalized
feed | | 4. Reasoning & editorial agents | 🟡 Harness hitting DB and publishing integration tested | Agents refactored,
adapters upgraded, dry-run tests under `tests/agents/`/`tests/adapters/`, and the harness now runs against MariaDB via
`agents/common/normalized_article_repository.py`,`agents/common/editorial_harness_runner.py`, and
`scripts/dev/run_agent_chain_harness.py`(`tests/agents/common/test_*` cover the flow) with a nightly dry-run in
`.github/workflows/editorial-harness.yml`. The runner now supports an opt-in publish path and safe token gating for
sandbox/CI flows. | Need to wire harness metrics into Grafana and tie outputs to the publishing checklist | | 5.
Publishing & e2e verification | 🟡 Partially started → 🟢 Expanded (tests & gating updates) | Lightweight Django publisher
application added at `agents/publisher/`— includes`manage.py`, sample articles, templates and ingestion command
(`agents/publisher/news/sample_articles.json`). Editorial harness publishing integration is now opt-in, token-gated for
sandboxes, and tests added to exercise publishing flows. | Needs production authentication/approval workflows, audit
logs, and final collector wiring for live traffic | | 7. Observability & harness | 🟢 Dashboards+alerts seeded | Grafana
JSON + provisioning (`docs/grafana/`, including`editorial-harness- dashboard.json`) now mirrors the three curated
dashboards tracked under `monitoring/dashboards/generated/`, adapter alert rules (`docs/monitoring/adapter-alert-
rules.yml`), trace collector updates, and the live Grafana instance has been pruned to those same
Business/Operations/System dashboards | Need stage-by-stage counters wired to dashboards and CI harness for canary runs
| | 8. Rollouts & safety | 🟡 Process drafted | `docs/mistral_adapter_rollout.md`, adapter spec/playbook outline staging
expectations | Need gating hooks tied to live-run KPIs and manual approval checklist |

Stages and success criteria:

1. Stage 0 — Setup & baseline

- **Status:** ✅ Complete. Dev setup instructions (`docs/dev-setup.md`) and smoke test`tests/smoke/test_stage0_env.py`
  validate the canonical conda env, compose stack, and required repo files. Canary URL list lives in
  `scripts/dev/canary_urls.txt` to keep runs deterministic.

- Reproducible branch and deterministic dev environment

- Services: MariaDB, Redis, Chroma (brought up via `scripts/dev/docker-compose.e2e.yml`)

- Systemd-managed agent fleet can be cycled with `infrastructure/systemd/scripts/enable_all.sh`(wrappers install into`/usr/local/bin` for sudo operators)

- Tests: unit + smoke tests run locally

1. Stage 1 — Crawl & fetch verification

- **Status:** 🟡 Partially complete. Crawl4AI is the primary runner (`agents/crawler/crawl4ai_adapter.py` +
  `scripts/ops/run_crawl_schedule.py`) and profile-driven scheduling is live (`config/crawl_profiles/`). Crawler → HITL
  flow, metadata payloads, and adaptive metrics are documented in `article_proc_path.md` and
  `crawl_and_scrape_stack.md`.

- Verify fetchers write raw HTML and metadata. Raw HTML references (`raw_html_ref`) are generated, but confirmation that
  `archive_storage/raw_html` holds every payload still depends on the archive agent wiring.

- Metrics: Stage B counters exist (see `common/stage_b_metrics.py`), yet no Grafana panel currently visualizes fetch success/latency.

1. Stage 2 — Ingestion & normalization

- **Status:** 🟡 Archive → Stage B wired. HITL service (`agents/hitl_service`) now drives`archive.queue_article`, and
  the archive agent records raw HTML snapshots plus ingest metrics (`tests/agents/test_archive_ingest_pipeline.py`,
  `tests/agents/test_archive_raw_html_snapshot.py`).

- Normalize raw HTML into canonical records once archive agent accepts the payload and persists normalized shapes.

- Metrics: ingest success rate, processing time → counters exist but still need Grafana wiring and DB visibility gates.

1. Stage 3 — Parsing & structure extraction

- **Status:** 🟡 Fixtures in CI. Trafilatura-first extraction remains the default with readability/jusText fallbacks, and
  deterministic assertions now live in `tests/parsing/test_canary_articles.py` powered by
  `tests/fixtures/canary_articles/`(promoted from`output/canary_*`).

- Extract title, author, publish_date, body via Stage B pipeline hooks; broaden fixtures to cover author/date edge cases and ensure normalized-feed linkage.

- Tests validating extraction correctness on a canary dataset exist; next step is extending coverage and adding automated refresh jobs for new canaries.

1. Stage 4 — Reasoning, fact-check and editorial agents

- **Status:** 🟡 Harness hitting DB. Agents (journalist, fact_checker, synthesizer, etc.) keep their standardized
  engines/dry-run tests (`tests/agents/test_*_mistral_engine.py`), the harness still powers integration tests
  (`agents/common/agent_chain_harness.py`,`tests/integration/test_agent_chain_harness.py`), and a new repository/runner
  pair now fetches normalized rows directly from MariaDB (`agents/common/normalized_article_repository.py`,
  `agents/common/editorial_harness_runner.py`,`scripts/dev/run_agent_chain_harness.py`).

- Agent chain produces a draft/brief/fact-check bundle from live records, persists traces back to `articles`
  (fact_check_trace/synth_trace), and emits acceptance metrics; the nightly workflow `.github/workflows/editorial-
  harness.yml`plus`scripts/dev/bootstrap_editorial_harness_db.py` keeps the dry-run exercising DB/Chroma while we
  plumb stored drafts into the publisher checklist (see `docs/editorial_harness_runbook.md`).

- Metrics: Stage B counters now expose `justnews_stage_b_editorial_harness_*`; follow`docs/grafana/editorial-harness-
  wiring.md` to import the dashboard, connect Prometheus, and track longitudinal acceptance trends.

1. Stage 5 — Publishing & end-to-end verification

- **Status:** 🟡 Partially started. The repository now includes a minimal Django-based publisher app (`agents/publisher`)
  with ingestion tooling and sample content allowing local publish/testing. This is a major step towards full e2e
  publishing verification.

- Evidence: `agents/publisher/manage.py`,`agents/publisher/news/views.py`,`agents/publisher/news/sample_articles.json`, initial migrations and tests are present on`dev/live-run-tests`.

- Gaps: integration with editorial agents, automated e2e tests that exercise the full pipeline (crawl → ingest → parse →
  editorial → publish), production-grade site validation, and CI gates are pending.

1. Observability & test harness

- **Status:** 🟢 Foundations ship with the repo. Grafana dashboards plus provisioning manifests live under
  `docs/grafana/`(including the new`editorial-harness-dashboard.json` that surfaces Stage 4 acceptance metrics),
  adapter alert rules are codified in `docs/monitoring/adapter-alert-rules.yml`, and tracing glue is updated in
  `monitoring/core/trace_collector.py`. The production instance now sources its Business Metrics, JustNews Operations,
  and JustNews System Overview dashboards directly from `monitoring/dashboards/generated/` and only those three
  dashboards remain published.

- Metrics, traces (correlation IDs), dashboards — need wiring to the new Grafana configs and exporter jobs.

- Canary dataset for E2E automation — partially addressed via `scripts/dev/canary_urls.txt`, but no automated crawl→publish harness yet.

### Note: GPU tests are disabled by default (safety)

For safety — to avoid accidental use of real GPU hardware that can exhaust resources and crash desktop apps — GPU-marked
tests are now disabled by default locally. The default test harness sets `TEST_GPU_AVAILABLE=false` and
`TEST_GPU_COUNT=0` in the test environment so running the full test-suite won't attempt real GPU allocations.

If you explicitly want to exercise GPU behavior (for real hardware or CI), opt in:

```
bash export TEST_GPU_AVAILABLE=true export TEST_GPU_COUNT=1
```

When running real GPU tests in CI or a dedicated machine, ensure
`USE_REAL_ML_LIBS=1` is set if you want the test processes to use the real
`torch` / `transformers` libraries; otherwise, the test harness installs
comprehensive mocks to simulate GPU behavior without requiring real hardware.

1. Rollouts & safety

   - **Status:** 🟡 Defined on paper. The adapter rollout guide (`docs/mistral_adapter_rollout.md`) and adapter spec/playbook include staging guidance, but there is no enforced gate tied to live-run KPIs.

   - Staging gating, manual approvals, audit logs — need integration with CI plus a checklist referencing success metrics, not just documentation.

## Immediate next steps

1. **Automate parsing validation (initial suite done):** Deterministic fixtures now live under `tests/fixtures/canary_articles/` and are exercised via `tests/parsing/test_canary_articles.py`; extend coverage (authors/publish dates) and wire a nightly refresh job for new canaries.

1. **Operationalize the editorial harness outputs:** With normalized rows flowing through `agents/common/normalized_article_repository.py` and the nightly workflow (`.github/workflows/editorial-harness.yml`) exercising the chain end-to-end, focus on plumbing the Stage B acceptance metrics into Grafana (`docs/grafana/editorial-harness-wiring.md` + `docs/grafana/editorial-harness-dashboard.json`), capturing the stored drafts for the publisher checklist (`docs/editorial_harness_runbook.md`), and documenting operational controls (`infrastructure/systemd/scripts/enable_all.sh`) so operators can recycle the service fleet safely.

1. **Stand up publishing + observability loops:** The repo now contains a publisher app enabling local publish testing. Implementations completed in this update:

- The editorial harness can now optionally publish accepted outputs back into the lightweight publisher DB using `--publish-on-accept` in `scripts/dev/run_agent_chain_harness.py` (opt-in to avoid accidental publishing in CI/production).

Running the entire test-suite locally (including gated integrations)
---------------------------------------------------------------

Some tests are gated behind environment flags and require external services
(MariaDB, Redis, Chroma) or provider credentials. By default these tests are
skipped during a local developer run to avoid failures if the required services
are not present.

To enable and run all gated tests locally (live DB / Chroma / provider + real
e2e tests):

1. Bring up the e2e infra stack (MariaDB, Redis, Chroma) using the provided docker-compose file:

```bash

# from the repo root

docker compose -f scripts/dev/docker-compose.e2e.yml up -d

```

1. Export the gating environment variables (and any provider credentials you need):

```bash
export RUN_REAL_E2E=1                # enable redis / mariadb-backed e2e tests export ENABLE_DB_INTEGRATION_TESTS=1 #
enable DB-backed integration tests export ENABLE_CHROMADB_LIVE_TESTS=1  # enable live Chroma tests export
RUN_PROVIDER_TESTS=1          # gated provider tests (HF/OpenAI) — still requires creds

## If you run provider tests, export API keys

export OPENAI_API_KEY="<your-openai-key>"

## OPENAI_MODEL, HF_TEST_MODEL, etc. can be set as needed

```

1. Use the helper wrapper to run pytest with the project env loaded (ensures global.env values are present):

```bash
./scripts/dev/run_e2e_with_env.sh -q   # will export the gating flags and invoke pytest

```

Notes & tips:

- The docker-compose file maps Chroma to the host port configured in `global.env` (3307 by default). If you need a different mapping, adjust `scripts/dev/docker-compose.e2e.yml` or set CHROMADB_PORT in your environment.

- If you want to run only a subset of gated tests, export the relevant flags individually (for example, only `ENABLE_CHROMADB_LIVE_TESTS=1` to run Chroma tests).

- In CI we bring up the same services (see `.github/workflows/editorial-harness.yml`) — we recommend mirroring the CI environment when troubleshooting integration failures.

- Stage‑B publishing metrics were added to `common/stage_b_metrics.py` (`justnews_stage_b_publishing_total` and `justnews_stage_b_publishing_latency_seconds`) and are recorded when the harness publishes accepted drafts.

- A helper `agents/common/publisher_integration.py` lets the harness write normalized articles into the publisher DB in a safe manner.

- A dedicated GitHub Actions workflow `/.github/workflows/e2e-publisher.yml` was added to run the publisher e2e test (`tests/e2e/test_publisher_publish_flow.py`) on branch pushes and manual dispatch.

- Grafana dashboard fragment `docs/grafana/publisher-dashboard.json` was added to show publish success/failure and latency.

1. **Wire Grafana/alerting for Stage 1–2 metrics and publishing:** Expose the new `ingest_*` / `raw_html_*` counters and the `justnews_stage_b_publishing_*` metrics via dashboards + alerts. Add CI gating on canary ingestion/publish metrics to prevent regressions.

Recent repo activities performed on branch `dev/live-run-tests`:

- Add `docs/dev-setup.md` — reproducible local setup + common commands

- Add `scripts/dev/canary_urls.txt` — minimal canary targets for controlled runs

- Add `tests/smoke/test_stage0_env.py` — fast smoke tests to validate the dev baseline

 - Add `tests/smoke/test_stage0_env.py` — fast smoke tests to validate the dev baseline

 - Add lightweight Django publisher app (`agents/publisher/`) with sample articles and manage command for manual ingestion.

 - Dashboard fixes: `agents/dashboard/dashboard_engine.py` now sources DB-driven `get_active_sources()`; `agents/dashboard/config.json` relaxed `news_sources` filtering (verification toggled off, `max_age_days` extended).

 - Performed restarts for dashboard and crawl4ai to load fixes during live-run troubleshooting.

Follow the README and `docs/dev-setup.md` to start reproducing locally and
iterate through stages.

---
### ✅ Recent updates (as of 4 Dec 2025)

- Fixed publish gating behavior in the editorial harness so that: when a `publish_token` is provided, verification is required; when no token is supplied publishing proceeds (useful for local dev). This resolved a failing unit test and clarified the expected behavior for local vs sandbox runs.

- Added tests to cover: publish without token (local/dev), publish with a valid token (CI sandbox), and skipped publishing when the token is invalid.

- Updated Stage 4 and Stage 5 statuses to reflect publishing test coverage and token-gating behavior.

- CI: added `/.github/workflows/e2e-publisher.yml` (e2e publisher test) and `/.github/workflows/editorial-harness-publish-sandbox.yml` (sandboxed harness publish) to exercise publish flows safely.

- CI: added `/.github/workflows/e2e-publisher.yml` (e2e publisher test) and `/.github/workflows/editorial-harness-publish-sandbox.yml` (sandboxed harness publish) to exercise publish flows safely.

- All targeted unit and e2e tests for the publishing flows pass locally with the current branch.

 - The publisher app now exposes a Prometheus-compatible `/metrics` endpoint and a JSON `/api/metrics/` endpoint; the CI sandbox verifies publishes by polling `/api/metrics/` as a KPI check.
