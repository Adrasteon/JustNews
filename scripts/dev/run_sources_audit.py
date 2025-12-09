#!/usr/bin/env python3
"""Run a set of read-only audit queries against the migrated MariaDB and print results.

Usage: source global.env && python scripts/dev/run_sources_audit.py
"""
import json
from database.utils.migrated_database_utils import create_database_service, execute_mariadb_query

QUERIES = {
    'describe_sources': "DESCRIBE sources;",
    'count_columns': (
        "SELECT\n  COUNT(*) AS total_rows,\n  COUNT(description) AS description_not_null,\n  COUNT(country) AS country_not_null,\n  COUNT(language) AS language_not_null,\n  SUM(paywall = TRUE) AS paywalled_count,\n  SUM(paywall IS NULL) AS paywall_null_count,\n  COUNT(paywall_type) AS paywall_type_not_null,\n  COUNT(last_verified) AS last_verified_not_null,\n  SUM(metadata IS NOT NULL) AS metadata_present\nFROM sources;"
    ),
    'sources_with_paywall_meta': (
        "SELECT id, domain, paywall, paywall_type, JSON_EXTRACT(metadata, '$.paywall_detection') AS paywall_meta, updated_at "
        "FROM sources WHERE JSON_EXTRACT(metadata, '$.paywall_detection') IS NOT NULL LIMIT 200;"
    ),
    'sources_with_modal_meta': (
        "SELECT id, domain, JSON_EXTRACT(metadata, '$.modal_handler') AS modal_info "
        "FROM sources WHERE JSON_EXTRACT(metadata, '$.modal_handler') IS NOT NULL LIMIT 100;"
    ),
    'recent_sources': (
        "SELECT id, domain, url, paywall, paywall_type, last_verified, updated_at "
        "FROM sources ORDER BY updated_at DESC LIMIT 100;"
    ),
    'article_source_map_modal_count': (
        "SELECT COUNT(*) AS modal_rows FROM article_source_map WHERE metadata IS NOT NULL AND JSON_EXTRACT(metadata, '$.modal_handler') IS NOT NULL;"
    ),
    'article_source_map_modal_samples': (
        "SELECT id, article_id, source_url_hash, JSON_EXTRACT(metadata, '$.modal_handler') AS modal_info, created_at "
        "FROM article_source_map WHERE JSON_EXTRACT(metadata, '$.modal_handler') IS NOT NULL LIMIT 200;"
    ),
}


def run():
    svc = create_database_service()
    results = {}
    for name, q in QUERIES.items():
        try:
            rows = execute_mariadb_query(svc, q, fetch=True)
            # Some drivers return tuples; convert nested types to JSON-serializable
            try:
                results[name] = rows
            except Exception:
                # fallback to string representation
                results[name] = [str(r) for r in rows]
        except Exception as e:  # safeguard: keep this read-only and non-destructive
            results[name] = {'error': str(e)}
    print(json.dumps(results, indent=2, default=str))


if __name__ == '__main__':
    run()
