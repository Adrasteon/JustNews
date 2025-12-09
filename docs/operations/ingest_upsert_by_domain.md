# Ingest upsert: canonical-by-domain (operator & developer notes)

Summary
- The ingestion pipeline now prefers updating an existing `sources` record by `domain` when ingesting a new article. This prevents creating duplicate `sources` rows for the same publisher domain.

How it works
- On ingest we attempt an `UPDATE sources ... WHERE domain = %s` that merges new `metadata` into any existing `metadata` using `JSON_MERGE_PATCH` and updates `canonical` + `updated_at`.
- If no existing domain row is found (UPDATE affected 0 rows), the old INSERT path is used to create a new `sources` row.
- Article-level `extraction_metadata.modal_handler` remains merged into the upsert's `metadata` so modal signals persist at source level.

Operational notes
- This change is intentionally conservative: we prefer in-place update by domain and do not delete or archive historical rows (the consolidation tool previously added handles historical duplicates).
- Recommended rollout:
  1. Run the consolidation tool to establish canonical rows and annotate duplicates with `canonical_source_id`.
  2. Enable the domain-preferred ingestion upsert (already implemented) to prevent new duplicates.
  3. Monitor metrics and inspect `sources` for any false merges due to domain collisions.

Developer notes
- The upsert logic is implemented in `agents/common/ingest.py` inside `ingest_article_db`.
- The change merges metadata using `JSON_MERGE_PATCH` — depending on your MariaDB version, JSON merge behavior should be validated on staging before production.
