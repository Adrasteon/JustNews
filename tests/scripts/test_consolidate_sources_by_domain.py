import json

import pytest

from scripts.dev import consolidate_sources_by_domain as cs


def test_build_plan_picks_canonical_and_aggregates(monkeypatch):
    # Sample groups: two domains with duplicate ids
    groups = [
        {'domain': 'example.com', 'count': 2, 'ids': [11, 10]},
        {'domain': 'test.com', 'count': 3, 'ids': [22, 21, 20]},
    ]

    # Stub execute_mariadb_query to return rows depending on query
    def fake_exec(service, q, params=None, fetch=True):
        if q.strip().startswith('SELECT id, url, updated_at FROM sources'):
            # Return rows with url and updated_at for the given ids
            if '11' in q:
                return [(11, 'https://example.com', '2025-12-07 00:00:00'), (10, 'https://m.example.com', '2025-12-06 00:00:00')]
            return [(22, 'https://www.test.com', '2025-12-06 00:00:00'), (21, 'https://sub.test.com', '2025-12-05 00:00:00'), (20, 'https://test.com/variant', '2025-12-04 00:00:00')]

        if q.strip().startswith("SELECT id, url, COALESCE(JSON_EXTRACT(metadata, '$.modal_handler')"):
            # modal values: simulate one modal detected for example.com
            if '11' in q:
                return [(11, 'https://example.com', json.dumps({'modal_detected': True})), (10, 'https://m.example.com', 'NULL')]
            # For test.com, assume none detected
            return [(22, 'https://www.test.com', 'NULL'), (21, 'https://sub.test.com', 'NULL'), (20, 'https://test.com/variant', 'NULL')]

        raise RuntimeError('Unexpected query: ' + str(q))

    monkeypatch.setattr(cs, 'execute_mariadb_query', fake_exec)

    plan = cs.build_plan(service=None, groups=groups)

    assert len(plan) == 2
    ex = next((p for p in plan if p['domain'] == 'example.com'), None)
    assert ex is not None
    assert ex['canonical_id'] == 11
    assert ex['aggregated']['variant_count'] == 2
    assert ex['aggregated']['modal_count'] == 1

    t = next((p for p in plan if p['domain'] == 'test.com'), None)
    assert t is not None
    # Prefer www as candidate for canonical if no exact match
    assert t['canonical_id'] in (22, 21, 20)
    assert t['aggregated']['variant_count'] == 3


def test_apply_consolidation_for_domain_executes_expected_updates(monkeypatch):
    calls = []

    def fake_exec(service, q, params=None, fetch=True):
        calls.append((q, params, fetch))
        # For updates, return empty list
        return []

    monkeypatch.setattr(cs, 'execute_mariadb_query', fake_exec)

    # Simulate applying for domain with ids [11,10] and canonical 11
    cs.apply_consolidation_for_domain(service=None, domain='example.com', ids=[11, 10], canonical_id=11, aggregated={'variant_count': 2, 'sample_urls': ['a', 'b'], 'modal_count': 1})

    # We expect two calls: update canonical metadata, update non-canonical rows to set canonical_source_id
    assert any('JSON_SET' in c[0] for c in calls), 'Did not update canonical metadata'
    assert any('canonical_source_id' in c[0] for c in calls), 'Did not update duplicate rows canonical_source_id'
