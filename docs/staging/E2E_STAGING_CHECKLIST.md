# E2E Staging Checklist — Crawl → HITL → Editorial → Publish (+ Training & KG)

This runbook describes a step-by-step staging validation for a full end-to-end run across the JustNews pipeline. It is intended for operators and SREs who will validate a staged environment (or pre-production cluster) that mirrors production configuration.

Objective
- Validate the full pipeline: crawl → raw_html archive → ingest normalization → parsing/extraction → HITL labeling → editorial harness → publish → training / ModelStore and KG ingestion.
- Check monitoring, alerts and runbooks behave as expected under normal/failed interactions.

Prerequisites (staging environment)
- Database (MariaDB) accessible and seeded for staging; connection configured via environment variables or `/etc/justnews/global.env`.
- ChromaDB (or configured vector DB) available for embedding tests.
- GPUs present or emulated if testing orchestrator features (or an orchestrator mock with job/lease simulation).
- Crawl4AI runtime present with browsers installed (or a stubbed adapter for offline canonical tests).
- Secrets and credentials are loaded into the environment (or an operator-managed staging vault).
- Canonical conda environment available: `${CANONICAL_ENV:-justnews-py312}`.

High-level checklist (short)
1. Validate infra & connections
2. Run crawl → archive → ingest smoke tests
3. Run parsing/extraction parity checks (Crawl4AI vs Trafilatura) on a canary set
4. Test HITL roundtrip (submit candidate → label → ingest)
5. Run editorial harness dry-run and publish flow to the staging publisher instance
6. Run training/ModelStore sanity checks and KG ingestion checks
7. Validate metrics, dashboards and alerts; exercise a safe alert to confirm runbook
8. Post-mortem: store artifacts, runbook update, and sign-off

Detailed Step-by-step validation

Step 0 — Setup the staging shell (operator)
- Activate canonical environment and export staging secrets:

```bash
# activate environment
conda activate ${CANONICAL_ENV:-justnews-py312}

# load environment (operator-managed)
# prefer a secure store; local fallback uses repo copy
source /etc/justnews/global.env || source global.env

# optional: set debug/controlled flags
export JUSTNEWS_ENV=staging
export ENABLE_CANARY_RUN=1
```

Step 1 — Infrastructure & connectivity
- Validate DB connectivity and schema migration state:

```bash
python scripts/dev/db_check.py  # or use your site-specific check utility
```

- Confirm Chroma/embedding store is reachable (sample ping or status endpoint)

Step 2 — Crawl → raw_html archive smoke test
- Trigger a short profile-driven crawl (dry-run then live) for a single canary domain: ensure raw_html is persisted

```bash
# dry run (no writes)
PYTHONPATH=$(pwd) python scripts/ops/run_crawl_schedule.py --dry-run --profiles config/crawl_profiles --sites canary.example.com

# live (small set)
PYTHONPATH=$(pwd) python scripts/ops/run_crawl_schedule.py --profiles config/crawl_profiles --sites canary.example.com --max_articles_per_site 2
```

Validate:
- Raw html exists under the configured `JUSTNEWS_RAW_HTML_DIR` path
- Ingest pipeline metrics register the ingest events (`raw_html_ingested_total`, `ingest_success_total`)

Step 3 — Parsing & extraction parity checks
- Run the canary fixture test and then parity checks comparing Crawl4AI vs Trafilatura (a small subset)

```bash
# unit/fixture smoke checks
PYTHONPATH=$(pwd) scripts/dev/pytest.sh tests/parsing/test_canary_articles.py -q

# parity evaluation (example harness / scripts present in evaluation/)
PYTHONPATH=$(pwd) python evaluation/run_parity_check.py --fixtures tests/fixtures/canary_articles --report output/parity_report.json
```

Validate:
- `tests/parsing/test_canary_articles.py` passes in the staging environment
- Parity report shows acceptable thresholds for title, body, publish_date; otherwise flag a manual review

Step 4 — HITL validation (submit, label, ingest)
- Submit a candidate manually or via a test helper: ensure it appears in the HITL staging endpoint, label it, forward, and confirm ingestion result

```bash
# submit a test candidate (simplified, replace host/port as needed)
curl -X POST http://localhost:8001/hitl/submit -H 'Content-Type: application/json' \
  -d '{"url": "https://canary.example.com/test","html": "<html>...</html>","source":"staging-canary"}'

# check HITL queue
curl http://localhost:8001/hitl/queues

# label the candidate (simulate reviewer)
curl -X POST http://localhost:8001/hitl/label -H 'Content-Type: application/json' \
  -d '{"candidate_id": "<id>", "label": "approved", "reviewer": "staging-team"}'
```

Validate:
- Candidate advances to `ingestion_status='forwarded'` and appears in MariaDB ingest tables
- Archive/ingest metrics show increased counts

Step 5 — Editorial harness and publish flow
- Run the editorial harness should it be configured for dry-run or an opt-in publish flow

```bash
# run editorial harness dry-run
PYTHONPATH=$(pwd) scripts/dev/pytest.sh tests/agents/common/test_editorial_harness_dryrun.py -q

# dry-run editorial harness via helper runner
PYTHONPATH=$(pwd) python scripts/dev/run_agent_chain_harness.py --dry-run --limit 1

# if publish path is permitted in staging, trigger the publish flow
PYTHONPATH=$(pwd) python scripts/dev/run_agent_chain_harness.py --publish --limit 1
```

Validate:
- Drafts and editorial outputs saved in DB; publisher receives publish events and test content is visible in staging publisher UI
- `tests/e2e/test_publisher_publish_flow.py` should pass

Step 6 — Training & ModelStore sanity checks
- Validate ModelStore path, model artifacts and training pipeline invocation(s)

```bash
# check ModelStore state and availability
ls ${MODEL_STORE_ROOT:-/var/models}

# run a small training harness (non-production) against staging datasets
evaluation/run_train_example.sh --dataset tests/fixtures/train_small
```

Validate:
- New model artifact(s) appear in ModelStore location
- Training job logs and metrics are recorded

Step 7 — Knowledge-Graph / Knowledge ingestion
- If the KG pipeline exists: ingest a small set and verify connectivity and queryable entities

```bash
# run KG ingestion stub
python agents/knowledge/ingest_test.py --file tests/fixtures/kg_sample.json

# query KG - sanity check
python agents/knowledge/query_test.py --entity "canary company"
```

Validate:
- Entities recorded and query returns expected results

Step 8 — Observability & alerting
- Confirm dashboards show ingestion, extraction and publish rates
- Exercise a safe alert (e.g. throttle ingestion metric to trigger an alert rule) and confirm Pager/Alertmanager behavior

Step 9 — Final sign-off & clean-up
- Export canary artifacts to `output/` and capture logs for retention
- Document any anomalies or follow-up remediation actions in the runbook
- If tests pass, consider a controlled promotion to pre-prod/production following the release gating policy

Helpful notes & safety
- Use small limits: `--max_articles_per_site 2` or `--limit 1` to limit scope
- Do not use production credentials or endpoints from a temporary staging script unless authorized
- Keep a runbook entry with contact/rotations for any alert we plan to exercise

Troubleshooting & quick checks
- DB: `SELECT * FROM articles WHERE source='staging-canary' ORDER BY created_at DESC LIMIT 10;`
- Raw html path: `ls $JUSTNEWS_RAW_HTML_DIR | tail -n 20`
- Prometheus metrics: `curl http://localhost:9100/metrics | grep ingest`
- Grafana: open the ingest dashboards and verify the canary widgets reflect the test run

Appendix: Common commands
```bash
# run complete short smoke suite
scripts/dev/staging_run_smoke.sh

# run individual tests
PYTHONPATH=$(pwd) pytest tests/parsing/test_canary_articles.py -q
PYTHONPATH=$(pwd) pytest tests/e2e/test_publisher_publish_flow.py -q
```

If you'd like, I can additionally scaffold the CI job for a staging-run smoke test that executes the key bits above and uploads artifacts to `output/` for triage and retention.
