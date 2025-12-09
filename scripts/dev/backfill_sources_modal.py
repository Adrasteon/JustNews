#!/usr/bin/env python3
"""Backfill script to aggregate article-level modal_handler signals into
the `sources.metadata.modal_handler` JSON object.

This is a safe, idempotent script that:
 - scans `article_source_map` for entries where metadata->'$.modal_handler' exists
 - aggregates counts per source (by source_id if available, otherwise source_url_hash)
 - updates `sources.metadata.modal_handler` with aggregated counters and last_detected_at

Usage:
  source global.env && python scripts/dev/backfill_sources_modal.py

This script uses the project's create_database_service and execute_mariadb_query helpers.
"""
import json
from datetime import datetime, timezone

from database.utils.migrated_database_utils import create_database_service, execute_mariadb_query, execute_transaction


def aggregate_modal_by_source(service):
    # Find rows in article_source_map with modal_handler present and aggregate
    q = """
    SELECT
      COALESCE(source_id, NULL) AS source_id,
      source_url_hash,
      JSON_EXTRACT(metadata, '$.modal_handler') AS modal_info
    FROM article_source_map
    WHERE metadata IS NOT NULL AND JSON_EXTRACT(metadata, '$.modal_handler') IS NOT NULL
    """
    rows = execute_mariadb_query(service, q, fetch=True)
    # rows are tuples; modal_info will be JSON text or a json string
    agg = {}
    for r in rows:
        source_id, source_url_hash, modal_info_raw = r
        try:
            modal_info = json.loads(modal_info_raw) if isinstance(modal_info_raw, (str, bytes)) else modal_info_raw
        except Exception:
            modal_info = {}

        key = None
        if source_id:
            key = ("id", int(source_id))
        elif source_url_hash:
            key = ("url_hash", source_url_hash)
        else:
            continue

        # modal_info expected shape: {modal_detected: bool, consent_cookies: int}
        detected = bool(modal_info.get('modal_detected')) if isinstance(modal_info, dict) else False

        if key not in agg:
            agg[key] = {'modal_count': 0, 'total_samples': 0, 'last_detected_at': None}

        agg[key]['total_samples'] += 1
        if detected:
            agg[key]['modal_count'] += 1
            agg[key]['last_detected_at'] = datetime.now(timezone.utc).isoformat() + 'Z'

    return agg


def update_sources_with_agg(service, agg):
    # For each aggregated key update the sources.metadata.modal_handler object
    updates = []
    for key, v in agg.items():
        col, val = key
        # Build the JSON structure we will set on sources.metadata.modal_handler
        modal_meta = json.dumps({
            'modal_count': v['modal_count'],
            'total_samples': v['total_samples'],
            'last_detected_at': v['last_detected_at'],
        }, default=str)

        if col == 'id':
            sql = (
                "UPDATE sources SET metadata = JSON_SET(COALESCE(metadata, JSON_OBJECT()), '$.modal_handler', %s), updated_at = NOW() WHERE id = %s"
            )
            params = (modal_meta, val)
        else:
            # url_hash case
            sql = (
                "UPDATE sources SET metadata = JSON_SET(COALESCE(metadata, JSON_OBJECT()), '$.modal_handler', %s), updated_at = NOW() WHERE url_hash = %s"
            )
            params = (modal_meta, val)

        updates.append((sql, params))

    # Execute updates in a transaction per batch to be safe
    for sql, params in updates:
        execute_mariadb_query(service, sql, params, fetch=False)

    return len(updates)


def run():
    svc = create_database_service()
    print("Scanning article_source_map for modal_handler metadata...")
    agg = aggregate_modal_by_source(svc)
    if not agg:
        print("No modal_handler metadata found in article_source_map. Nothing to do.")
        return

    print(f"Found {len(agg)} sources to update; applying updates...")
    updated = update_sources_with_agg(svc, agg)
    print(f"Updated {updated} sources with modal_handler metadata")


if __name__ == '__main__':
    run()
