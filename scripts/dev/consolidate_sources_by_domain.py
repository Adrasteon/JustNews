#!/usr/bin/env python3
"""Consolidate duplicate `sources` rows by domain into a single canonical source.

This tool is operator-facing and supports two main modes:
 - preview (default / dry-run): show the consolidation plan for domains with duplicate rows
 - apply: apply the consolidation to the DB by annotating duplicates with a
   `canonical_source_id` and aggregating simple variant statistics into the
   canonical row's `metadata.variants` JSON object.

Usage:
  source global.env && python scripts/dev/consolidate_sources_by_domain.py --preview --limit 50
  source global.env && python scripts/dev/consolidate_sources_by_domain.py --apply --limit 20

This script is written to be safe and idempotent. It will ensure the `canonical_source_id`
column exists (creates it if missing) and uses transactional updates per-domain.

Notes
- The current consolidation strategy picks a canonical row for each domain in this order:
  1. Prefer a canonical url `https://{domain}` when present
  2. Otherwise pick the most recently updated row
  3. As a final fallback use the lowest id

Developer / operator guidance: run with `--preview` first, verify results, then run with `--apply`
and a small `--limit` for a phased rollout. Back up the DB before applying to production.
"""
import argparse
import json
import sys
from datetime import datetime

from database.utils.migrated_database_utils import (
    create_database_service,
    execute_mariadb_query,
    execute_transaction,
)


def find_duplicate_domains(service, limit=None, domain_filter=None):
    q = (
        "SELECT domain, COUNT(*) AS cnt, GROUP_CONCAT(id ORDER BY updated_at DESC SEPARATOR ',') as ids "
        "FROM sources WHERE domain IS NOT NULL GROUP BY domain HAVING cnt > 1 ORDER BY cnt DESC"
    )
    if limit:
        q = q + f" LIMIT {int(limit)}"
    if domain_filter:
        q = (
            "SELECT domain, COUNT(*) AS cnt, GROUP_CONCAT(id ORDER BY updated_at DESC SEPARATOR ',') as ids "
            "FROM sources WHERE domain = %s GROUP BY domain HAVING cnt > 1"
        )
        rows = execute_mariadb_query(service, q, params=(domain_filter,), fetch=True)
    else:
        rows = execute_mariadb_query(service, q, fetch=True)

    results = []
    for domain, cnt, ids in rows:
        id_list = [int(x) for x in ids.split(',') if x]
        results.append({'domain': domain, 'count': int(cnt), 'ids': id_list})

    return results


def pick_canonical(service, domain, ids):
    # Prefer a `https://{domain}` url in the group
    q = "SELECT id, url, updated_at FROM sources WHERE id IN (%s)" % ",".join(str(i) for i in ids)
    rows = execute_mariadb_query(service, q, fetch=True)

    # rows: list of tuples (id, url, updated_at)
    candidate = None
    domain_https = f"https://{domain}"
    domain_www = f"https://www.{domain}"

    latest_updated = None
    lowest_id = None

    for r in rows:
        rid, url, updated_at = r
        if url == domain_https:
            return int(rid)
        if url == domain_www:
            candidate = int(rid)

        # track latest updated
        if updated_at is not None:
            if latest_updated is None or updated_at > latest_updated[0]:
                latest_updated = (updated_at, int(rid))

        if lowest_id is None or rid < lowest_id:
            lowest_id = int(rid)

    if candidate:
        return candidate
    if latest_updated:
        return latest_updated[1]
    return lowest_id


def aggregate_variant_data(service, ids, sample_limit=5):
    # Collect sample urls and modal counts from metadata
    q = "SELECT id, url, COALESCE(JSON_EXTRACT(metadata, '$.modal_handler'), 'NULL') as modal FROM sources WHERE id IN (%s)" % ",".join(str(i) for i in ids)
    rows = execute_mariadb_query(service, q, fetch=True)

    sample_urls = []
    modal_count = 0
    total = 0
    for rid, url, modal in rows:
        total += 1
        if url and len(sample_urls) < sample_limit:
            sample_urls.append(url)
        try:
            if modal and modal not in ('NULL', None):
                mm = json.loads(modal)
                if isinstance(mm, dict) and mm.get('modal_detected'):
                    modal_count += 1
        except Exception:
            continue

    return {'variant_count': total, 'sample_urls': sample_urls, 'modal_count': modal_count}


def ensure_canonical_column(service):
    # Add the canonical_source_id column if it doesn't exist
    # Using IF NOT EXISTS style: MariaDB supports ADD COLUMN IF NOT EXISTS
    q = "ALTER TABLE sources ADD COLUMN IF NOT EXISTS canonical_source_id BIGINT NULL"
    execute_mariadb_query(service, q, fetch=False)


def apply_consolidation_for_domain(service, domain, ids, canonical_id, aggregated):
    # Update canonical row metadata with aggregated variant info
    modal_meta = json.dumps(aggregated)

    update_canonical = (
        "UPDATE sources SET metadata = JSON_SET(COALESCE(metadata, JSON_OBJECT()), '$.variants', %s), updated_at = NOW() WHERE id = %s"
    )
    execute_mariadb_query(service, update_canonical, params=(modal_meta, canonical_id), fetch=False)

    # Set canonical_source_id on non-canonical rows
    non_can = [str(i) for i in ids if int(i) != int(canonical_id)]
    if non_can:
        # Use a safe parameterized multi-update
        q = "UPDATE sources SET canonical_source_id = %s WHERE id IN (%s)" % (
            int(canonical_id), ",".join(non_can)
        )
        execute_mariadb_query(service, q, fetch=False)


def build_plan(service, groups):
    plan = []
    for g in groups:
        domain = g['domain']
        ids = g['ids']
        canonical_id = pick_canonical(service, domain, ids)
        aggregated = aggregate_variant_data(service, ids)
        plan.append({
            'domain': domain,
            'count': g['count'],
            'ids': ids,
            'canonical_id': canonical_id,
            'aggregated': aggregated,
        })
    return plan


def main(argv=None):
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Apply changes (skips preview).')
    parser.add_argument('--limit', type=int, help='Limit number of domain groups to process (preview or apply).')
    parser.add_argument('--domain', type=str, help='Restrict to a single domain for targeted runs.')
    parser.add_argument('--sample', type=int, default=5, help='Number of sample urls to capture per domain')
    args = parser.parse_args(argv)

    svc = create_database_service()

    groups = find_duplicate_domains(svc, limit=args.limit, domain_filter=args.domain)
    if not groups:
        print('No duplicate domains found. Nothing to do.')
        return 0

    plan = build_plan(svc, groups)

    if not args.apply:
        print(json.dumps({'mode': 'preview', 'count': len(plan), 'plan': plan}, default=str, indent=2))
        return 0

    # Apply path
    print(f'Applying consolidation for {len(plan)} domains...')
    ensure_canonical_column(svc)

    applied = 0
    for p in plan:
        # Build the queries needed for this domain and run them in a single
        # transaction so we don't leave the DB in a partial state for that
        # domain.
        try:
            # Prepare canonical update
            modal_meta = json.dumps(p['aggregated'])
            update_canonical = (
                "UPDATE sources SET metadata = JSON_SET(COALESCE(metadata, JSON_OBJECT()), '$.variants', %s), updated_at = NOW() WHERE id = %s"
            )

            non_can_ids = [str(i) for i in p['ids'] if int(i) != int(p['canonical_id'])]
            queries = [update_canonical]
            params_list = [(modal_meta, int(p['canonical_id']))]

            if non_can_ids:
                q = "UPDATE sources SET canonical_source_id = %s WHERE id IN (%s)" % (
                    int(p['canonical_id']), ",".join(non_can_ids)
                )
                queries.append(q)
                params_list.append(None)

            success = execute_transaction(svc, queries, params_list)
            if success:
                applied += 1
            else:
                print(f'Error applying domain {p["domain"]}: transaction failed')
        except Exception as e:
            print(f'Error applying domain {p["domain"]}: {e}')

    print(f'Applied consolidation for {applied} domains')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
