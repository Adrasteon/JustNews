"""Ingest adapter helpers for mapping crawler payloads to DB-ready operations.

This module provides small, dependency-free helper functions used by agents to
prepare upsert statements and article_source_map payloads. For Phase 1 these are
stubs designed to be used by unit tests and later wired to the real DB code or
agent-driven transactions via `mcp_bus`.
"""
import json
from typing import Any

# This module intentionally avoids DB driver imports at top-level. For
# production use we route to the migrated MariaDB helper when needed.


def build_source_upsert(payload: dict[str, Any]) -> tuple[str, tuple]:
    """Return a MariaDB-compatible upsert SQL and params for `sources`.

    Uses `INSERT ... ON DUPLICATE KEY UPDATE` and does not rely on RETURNING.
    The caller should obtain the inserted id via cursor.lastrowid when needed.
    """
    sql = (
        "INSERT INTO sources (url, url_hash, domain, canonical, metadata, created_at)"
        " VALUES (%s, %s, %s, %s, %s, NOW())"
        " ON DUPLICATE KEY UPDATE canonical=VALUES(canonical), metadata=VALUES(metadata), updated_at=NOW();"
    )

    # Merge relevant source-level metadata.
    # Source upserts normally carry publisher_meta; include modal_handler from
    # extraction_metadata when present so source-level signals can persist.
    publisher_meta = dict(payload.get('publisher_meta', {}) or {})
    extraction_meta = payload.get('extraction_metadata') or {}
    modal = extraction_meta.get('modal_handler') if isinstance(extraction_meta, dict) else None
    if modal is not None:
        # Prefer preserving any existing keys, but set or override modal_handler
        publisher_meta = dict(publisher_meta)
        publisher_meta['modal_handler'] = modal

    params = (
        payload.get('url'),
        payload.get('url_hash'),
        payload.get('domain'),
        payload.get('canonical'),
        json.dumps(publisher_meta),
    )

    return sql, params


def build_article_source_map_insert(article_id: int, source_payload: dict[str, Any]) -> tuple[str, tuple]:
    """Build SQL and params for inserting into article_source_map.

    Expects article_id and source_payload with url_hash, confidence, paywall_flag, and extraction_metadata
    """
    sql = (
        "INSERT INTO public.article_source_map (article_id, source_url_hash, confidence, paywall_flag, metadata, created_at)"
        " VALUES (%s, %s, %s, %s, %s, now());"
    )

    params = (
        article_id,
        source_payload.get('url_hash'),
        source_payload.get('confidence', 0.5),
        source_payload.get('paywall_flag', False),
        json.dumps(source_payload.get('extraction_metadata', {})),
    )

    return sql, params


def canonical_selection_rule(candidates: list) -> dict[str, Any]:
    """Simple canonical selection implementation used for testing.

    candidates: list of dicts with keys ['source_id'|'url_hash', 'confidence', 'timestamp', 'matched_by']
    Returns chosen candidate dict.
    """
    if not candidates:
        return {}

    # Sort by confidence desc, timestamp desc, matched_by==ingest preferred
    def score(c):
        conf = float(c.get('confidence', 0.0))
        ts = c.get('timestamp') or ''
        matched = 1 if c.get('matched_by') == 'ingest' else 0
        return (conf, ts, matched)

    sorted_candidates = sorted(candidates, key=score, reverse=True)
    return sorted_candidates[0]


def ingest_article(article_payload: dict[str, Any], db_execute) -> dict[str, Any]:
    """High-level ingest helper that performs a transactional upsert of source,
    inserts article_source_map and returns the chosen canonical candidate using
    the simple canonical selection rule.

    db_execute: callable(sql, params) -> returns lastrowid or None. This is
    intentionally abstract to allow using sqlite3 in-memory tests or a real
    DB driver in production.
    """
    # Upsert source
    source_sql, source_params = build_source_upsert(article_payload)
    source_id = db_execute(source_sql, source_params)

    # Simulate obtaining article_id (in a real system articles table would be used)
    article_id = article_payload.get('article_id') or 1

    # Insert article_source_map
    asm_sql, asm_params = build_article_source_map_insert(article_id, article_payload)
    db_execute(asm_sql, asm_params)

    # For canonical selection, fetch candidates (in tests we will pass them)
    # Here, we simulate by returning the single candidate created
    candidate = {
        'source_id': source_id,
        'url_hash': article_payload.get('url_hash'),
        'confidence': article_payload.get('confidence', 0.5),
        'timestamp': article_payload.get('timestamp'),
        'matched_by': article_payload.get('matched_by', 'ingest')
    }

    canonical = canonical_selection_rule([candidate])

    # Do not execute update by default; leave to orchestrator or DB stored proc

    return {
        'source_id': source_id,
        'article_id': article_id,
        'canonical': canonical
    }


def ingest_article_db(article_payload: dict[str, Any], dsn: str) -> dict[str, Any]:
    """Execute the ingest using the migrated MariaDB-backed service.

    This will perform the source upsert and insert article_source_map inside
    a single transaction and return the chosen canonical candidate.
    """
    # Use the migrated DB service so we don't depend on a specific DB driver
    from database.utils.migrated_database_utils import create_database_service

    service = create_database_service()

    source_sql, source_params = build_source_upsert(article_payload)
    asm_sql, asm_params = build_article_source_map_insert(article_payload.get('article_id', 1), article_payload)

    try:
        conn = service.get_connection()
        cursor = conn.cursor()
        try:
            # Prefer canonical upsert by domain: try UPDATE by domain first so
            # we avoid creating many duplicate rows for the same publisher.
            domain = article_payload.get('domain')
            source_id = None

            if domain:
                # Merge the provided metadata into any existing metadata JSON using
                # JSON_MERGE_PATCH for a safe, non-destructive merge.
                # Note: if the UPDATE affected 0 rows we fall back to inserting.
                try:
                    # Build merged metadata param using same publisher_meta logic
                    # as build_source_upsert to ensure modal_handler is included.
                    merged_meta = source_params[4]
                    update_sql = (
                        "UPDATE sources SET canonical = %s, metadata = JSON_MERGE_PATCH(COALESCE(metadata, JSON_OBJECT()), %s), updated_at = NOW() WHERE domain = %s"
                    )
                    update_params = (article_payload.get('canonical'), merged_meta, domain)
                    cursor.execute(update_sql, update_params)
                    if getattr(cursor, 'rowcount', 0) > 0:
                        # Get the id we updated
                        lookup_cur = conn.cursor(dictionary=True, buffered=True)
                        lookup_cur.execute("SELECT id FROM sources WHERE domain = %s LIMIT 1", (domain,))
                        row = lookup_cur.fetchone()
                        try:
                            lookup_cur.close()
                        except Exception:
                            pass
                        source_id = row.get('id') if row else None
                except Exception:
                    # If the domain-based UPDATE failed for any reason, fall through
                    # to an INSERT below so ingestion continues.
                    source_id = None

            # If we did not update an existing row by domain, insert a new source
            if not source_id:
                cursor.execute(source_sql, source_params)
                # Obtain inserted id: prefer lastrowid
                source_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
            if not source_id:
                # Try to lookup by url_hash
                try:
                    # Use a buffered dictionary cursor on the same per-call connection
                    lookup_cur = conn.cursor(dictionary=True, buffered=True)
                    lookup_cur.execute("SELECT id FROM sources WHERE url_hash = %s", (article_payload.get('url_hash'),))
                    row = lookup_cur.fetchone()
                    lookup_cur.close()
                    source_id = row.get('id') if row else None
                except Exception:
                    source_id = None

            # Insert article_source_map
            cursor.execute(asm_sql, asm_params)

            # Commit transaction
            conn.commit()

            # Build candidate and canonical rule
            candidate = {
                'source_id': source_id,
                'url_hash': article_payload.get('url_hash'),
                'confidence': article_payload.get('confidence', 0.5),
                'timestamp': article_payload.get('timestamp'),
                'matched_by': article_payload.get('matched_by', 'ingest')
            }

            canonical = canonical_selection_rule([candidate])

            return {
                'source_id': source_id,
                'article_id': article_payload.get('article_id', 1),
                'canonical': canonical
            }
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
