import json

from agents.common.ingest import build_source_upsert


def test_build_source_upsert_includes_modal_handler():
    payload = {
        'url': 'https://example.com/article/1',
        'url_hash': 'hash1',
        'domain': 'example.com',
        'canonical': 'https://example.com',
        'publisher_meta': {'last_crawled': '2025-01-01T00:00:00Z'},
        'extraction_metadata': {'modal_handler': {'modal_detected': True, 'consent_cookies': 2}},
    }

    sql, params = build_source_upsert(payload)

    # params[4] should be the JSON serialized metadata
    metadata_json = params[4]
    metadata = json.loads(metadata_json)

    assert 'modal_handler' in metadata
    assert metadata['modal_handler']['modal_detected'] is True
    assert metadata['modal_handler']['consent_cookies'] == 2


def test_build_source_upsert_no_modal_keeps_publisher_meta():
    payload = {
        'url': 'https://example.com/article/2',
        'url_hash': 'hash2',
        'domain': 'example.com',
        'canonical': 'https://example.com',
        'publisher_meta': {'last_crawled': '2025-01-02T00:00:00Z'},
    }

    sql, params = build_source_upsert(payload)
    metadata = json.loads(params[4])
    assert metadata.get('last_crawled') == '2025-01-02T00:00:00Z'
    assert 'modal_handler' not in metadata
