# Dev helper scripts

This directory contains helper scripts for development operations such as clearing
the local development database and minimal reseeding.

scripts/dev/clear_and_reseed_dev_data.py
- Clears article-related tables in MariaDB and deletes the `articles` ChromaDB collection.
- By default the script does NOT reseed any data; use the following flags to reseed:
  - `--seed-articles` : recreate the minimal `articles` schema and seed one sample article (editorial harness)
  - `--seed-sources`  : repopulate the `sources` table only, using `scripts/news_outlets.py`
  - `--sources-file PATH` : optional path to a markdown/text file of source domains to seed (if omitted a default file in scripts/ops/... may be used)

Example: reseed only sources after a DB truncate:

```bash
python3 scripts/dev/clear_and_reseed_dev_data.py --confirm --seed-sources --sources-file scripts/ops/markdown_docs/agent_documentation/potential_news_sources.md
```

Make sure you understand these operations are destructive and intended for development only.

scripts/dev/verify_chroma_parity.py
- Verify one-to-one parity between MariaDB `articles` and the canonical Chroma `articles` collection.
- Returns exit code 0 on success, non-zero if mismatches are found (useful for CI checks).

Example:
```bash
PYTHONPATH=. python3 scripts/dev/verify_chroma_parity.py --collection articles --batch 500
```

Repair mode:
- Add `--repair` to instruct the script to attempt to fix parity issues by re-indexing missing or mismatched rows from MariaDB into Chroma.
- The script is deliberately conservative: pass `--confirm` to actually perform writes. Without `--confirm` `--repair` runs as a dry-run and returns non-zero just like a parity failure.
- By default repairs will upsert missing/mismatched documents into the target Chroma collection. Use `--delete-extras` to also delete Chroma documents that have no matching MariaDB row.
- A backup of affected Chroma documents will be written to the `--backup-dir` (defaults to `scripts/dev/backups`) before changes are made.
- If you need to avoid embedding model availability for repair (for example in a CI worker without models), pass `--skip-embeddings` and the script will upsert documents & metadata only.

Example (dry-run):
```bash
PYTHONPATH=. python3 scripts/dev/verify_chroma_parity.py --repair
```

Example (perform repair):
```bash
PYTHONPATH=. python3 scripts/dev/verify_chroma_parity.py --repair --confirm --backup-dir scripts/dev/backups
```

Run automatically after a live crawl
----------------------------------
- The `live_crawl_test.py` harness will run the parity verifier automatically at the end of the crawl when `PARITY_CHECK_ON_CRAWL` is set (defaults to enabled).
- To enable automatic repair after a crawl set `PARITY_REPAIR_ON_CRAWL=1` and to bypass the confirmation add `PARITY_REPAIR_CONFIRM_BYPASS=1` (dangerous — use carefully).
- Example: run crawl and then perform repair with backup:
```bash
PARITY_CHECK_ON_CRAWL=1 PARITY_REPAIR_ON_CRAWL=1 PARITY_REPAIR_CONFIRM_BYPASS=1 PYTHONPATH=. python3 live_crawl_test.py
```
