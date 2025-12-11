#!/usr/bin/env bash
# Helper script for operators: run a minimal smoke validation for staging
# Use this from repo root. Requires the canonical conda env active.
set -euo pipefail

# Safety environment defaults for staging smoke: avoid loading heavy model weights
# and cap concurrency to prevent resource saturation during operator smoke runs.
export MODEL_STORE_DRY_RUN=${MODEL_STORE_DRY_RUN:-1}
export FACT_CHECKER_DISABLE_MISTRAL=${FACT_CHECKER_DISABLE_MISTRAL:-1}
export JOURNALIST_DISABLE_MISTRAL=${JOURNALIST_DISABLE_MISTRAL:-1}
export SYNTHESIZER_DISABLE_MISTRAL=${SYNTHESIZER_DISABLE_MISTRAL:-1}

# Cap crawl concurrency to 1 site and small article budgets for smoke tests
export LIVE_CONCURRENT_SITES=${LIVE_CONCURRENT_SITES:-1}
export JUSTNEWS_TEST_MAX_ARTICLES_PER_SITE=${JUSTNEWS_TEST_MAX_ARTICLES_PER_SITE:-2}

CANONICAL_ENV=${CANONICAL_ENV:-justnews-py312}

echo "== Activate canonical env: ${CANONICAL_ENV} =="
# The script expects the operator to have already run `conda activate`
python -c "import sys; print('Python:', sys.executable)"

echo "\n== 1) Crawl smoke (dry-run) =="
PYTHONPATH=$(pwd) LIVE_CONCURRENT_SITES=${LIVE_CONCURRENT_SITES} python scripts/ops/run_crawl_schedule.py --dry-run --profiles config/crawl_profiles --sites canary.example.com || true

echo "\n== 2) Run parsing fixture smoke tests =="
PYTHONPATH=$(pwd) MODEL_STORE_DRY_RUN=${MODEL_STORE_DRY_RUN} FACT_CHECKER_DISABLE_MISTRAL=${FACT_CHECKER_DISABLE_MISTRAL} JOURNALIST_DISABLE_MISTRAL=${JOURNALIST_DISABLE_MISTRAL} SYNTHESIZER_DISABLE_MISTRAL=${SYNTHESIZER_DISABLE_MISTRAL} scripts/dev/pytest.sh tests/parsing/test_canary_articles.py -q || true

echo "\n== 3) Editorial harness dry-run =="
PYTHONPATH=$(pwd) MODEL_STORE_DRY_RUN=${MODEL_STORE_DRY_RUN} FACT_CHECKER_DISABLE_MISTRAL=${FACT_CHECKER_DISABLE_MISTRAL} JOURNALIST_DISABLE_MISTRAL=${JOURNALIST_DISABLE_MISTRAL} SYNTHESIZER_DISABLE_MISTRAL=${SYNTHESIZER_DISABLE_MISTRAL} python scripts/dev/run_agent_chain_harness.py --dry-run --limit 1 || true

echo "\n== 4) Publisher e2e smoke =="
PYTHONPATH=$(pwd) scripts/dev/pytest.sh tests/e2e/test_publisher_publish_flow.py -q || true

echo "\nSmoke run finished — check output/, logs, DB and dashboards for verification."