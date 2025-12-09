# Consolidate duplicate `sources` rows by domain — runbook

This runbook explains the purpose and safe operation of `scripts/dev/consolidate_sources_by_domain.py`.

Purpose
- Consolidate multiple `sources` rows that share the same `domain` into a single canonical source record per domain while preserving historical rows.
- The script marks duplicates with a `canonical_source_id` and aggregates simple `variants` statistics into the canonical row's `metadata.variants` object so downstream systems get a canonical single-row source while retaining provenance.

Key safety features
- Preview (dry-run) mode — returns a JSON plan showing chosen canonical ids, ids to be annotated, and aggregated variant statistics.
- The script will create a `canonical_source_id` column if missing instead of deleting rows, so it is non-destructive and reversible.
- The script runs per-domain transactions when applying to avoid partial state on failures and supports `--limit` and `--domain` for targeted operations.

Usage examples

Preview the top 20 duplicate domains:

```bash
source global.env
PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python scripts/dev/consolidate_sources_by_domain.py --limit 20
```

Preview for a specific domain:

```bash
source global.env
PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python scripts/dev/consolidate_sources_by_domain.py --domain example.com
```

Apply consolidation for a small set (careful — write operation):

```bash
source global.env
PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python scripts/dev/consolidate_sources_by_domain.py --apply --limit 5
```

Post-apply checks
- Re-run the preview command (without `--apply`) and confirm those domains now report a canonical id and duplicates annotated with `canonical_source_id`.

Recommended follow-ups
- Add a unique index on `domain` only after the consolidation process and verification window is completed.
- Optionally archive or delete duplicate rows after a retention/verification window; prefer archiving to preserve provenance.
