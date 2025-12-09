# Modal detection persistence — audit & backfill runbook

This document is an operator-focused runbook for the modal/detection audit and backfill tools included in the repository.

Purpose
- Provide step-by-step guidance to safely inspect and, where desired, backfill historical crawler-detected modal signals from article rows into the `sources.metadata.modal_handler` JSON object.

Files / scripts
- `scripts/dev/run_sources_audit.py`
  - Read-only audit that inspects `sources` and `article_source_map` for `paywall` and `modal_handler` metadata.
- `scripts/dev/backfill_sources_modal.py`
  - Idempotent backfill that aggregates article-level `modal_handler` observations and sets `sources.metadata.modal_handler` per source.

Safety notes (critical)
- Always run the audit first to understand the scope of the write operation you plan to apply — use `run_sources_audit.py` and inspect counts and sample rows.
- Backups: before running `backfill_sources_modal.py` in production, create a database snapshot or logical export of the affected tables (`sources` and `article_source_map`).
- The backfill is idempotent, but the current implementation performs in-place `UPDATE` queries — practice caution.

Recommended run steps

1. Prepare your environment (repo `global.env` or `/etc/justnews/global.env`):

```bash
# Load credentials into environment
source /etc/justnews/global.env  # operator-managed global env (preferred)
# Or fall back to the repo copy for dev machines
source global.env

# ensure canonical python environment
PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python scripts/dev/run_sources_audit.py
```

2. Inspect audit results and decide on scope to backfill.

3. Optional: run a test backfill in a staging environment with a subset of data or a test DB snapshot.

4. Run the backfill in production (only after backups and review):

```bash
source /etc/justnews/global.env
PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python scripts/dev/backfill_sources_modal.py
```

Post-run checks
- Re-run `run_sources_audit.py` after the backfill completes and verify `sources_with_modal_meta` contains the updated rows.
- Spot-check a few `sources` rows for correct `modal_count`, `total_samples` and `last_detected_at` values.

Developer notes and follow-ups
- The ingestion pipeline now merges any `extraction_metadata.modal_handler` present on newly ingested articles into the `sources.metadata` field during source upserts. See `agents/common/ingest.py` for the upsert implementation.
- Recommended improvements:
  - Add a `--dry-run` flag to `backfill_sources_modal.py` so operators can preview updates without committing them.
  - Allow limiting backfill scope (by domain, single source id or date range).
  - Add integration tests using a DB fixture to ensure backfill behavior is safe in CI.

Troubleshooting
- If `backfill_sources_modal.py` reports zero updates, you likely have no `article_source_map` rows with `metadata.modal_handler`. Run the audit tool first to confirm.
- For DB authentication issues when running via the conda environment, prefer the `scripts/run_with_env.sh` wrapper or ensuring your active environment matches the creds in `global.env`.
