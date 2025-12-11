#!/usr/bin/env python3
"""Verify parity between MariaDB `articles` table and Chroma `articles` collection.

Exits with non-zero code if any of the following checks fail:
 - counts mismatch between MariaDB and Chroma
 - any Maria article id missing from Chroma
 - any Chroma document id missing from Maria
 - any metadata mismatches for normalized_url or url_hash

Usage:
  PYTHONPATH=. python3 scripts/dev/verify_chroma_parity.py [--collection NAME] [--batch N]

Exit codes:
  0  OK / perfect parity
  1  Operational error (DB/Chroma unavailable)
  2  Parity check failed (mismatches found)
"""
from __future__ import annotations

import argparse
import sys
import os
import json
from datetime import datetime, timezone
from typing import Dict


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="Verify Chroma/MariaDB article parity")
    p.add_argument("--collection", default="articles", help="Chroma collection name (default: articles)")
    p.add_argument("--batch", type=int, default=500, help="Batch size when listing chroma docs (default 500)")
    p.add_argument("--repair", action="store_true", help="Attempt to repair parity by reindexing missing/mismatched docs")
    p.add_argument("--confirm", action="store_true", help="Actually perform repair operations (without this, --repair only performs a dry-run)")
    p.add_argument("--backup-dir", default="scripts/dev/backups", help="Directory to write Chroma backup payloads before modifying (default: scripts/dev/backups)")
    p.add_argument("--delete-extras", action="store_true", help="When repairing, delete Chroma docs that have no MariaDB row (use carefully)")
    p.add_argument("--skip-embeddings", action="store_true", help="When repairing, avoid re-computing embeddings (useful if model unavailable) - will still upsert documents/metadatas")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Lazy imports so script can be imported in CI without immediate runtime deps
    try:
        import chromadb
    except Exception as e:  # pragma: no cover - runtime environment required
        print(f"ERROR: chromadb not available: {e}", file=sys.stderr)
        return 1

    try:
        from database.utils.migrated_database_utils import create_database_service
    except Exception as e:  # pragma: no cover - runtime environment required
        print(f"ERROR: DB helpers not available: {e}", file=sys.stderr)
        return 1

    # Connect to MariaDB
    svc = create_database_service()
    conn = svc.get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, normalized_url, url_hash FROM articles")
    maria_rows = cur.fetchall() or []
    cur.close()
    conn.close()

    maria_map: Dict[str, Dict[str, str]] = {}
    for row in maria_rows:
        aid = str(row[0])
        normalized = row[1] or ""
        url_hash = row[2] or ""
        maria_map[aid] = {"normalized_url": normalized, "url_hash": url_hash}

    maria_ids = set(maria_map.keys())
    print(f"MariaDB: {len(maria_ids)} articles loaded")

    # Prefer to record parity & repair metrics when available; also use a logger
    try:
        from common.stage_b_metrics import get_stage_b_metrics
        from common.observability import get_logger
        metrics = get_stage_b_metrics()
        logger = get_logger(__name__)
    except Exception:
        metrics = None
        logger = None

    # Connect Chroma
    host = "localhost"
    port = 3307
    client = chromadb.HttpClient(host=host, port=port)

    collections = [c.name for c in client.list_collections()]
    if args.collection not in collections:
        print(f"ERROR: collection '{args.collection}' not found in Chroma (available: {collections})", file=sys.stderr)
        return 1

    coll = client.get_collection(args.collection)
    chroma_count = coll.count()
    print(f"Chroma collection '{args.collection}': {chroma_count} documents")

    # Iterate chroma docs in batches, accumulate mapping
    chroma_map: Dict[str, Dict[str, str]] = {}
    limit = args.batch
    offset = 0
    # The chroma client returns ids in 'ids' and metadata in 'metadatas'. We'll page until we've seen all.
    while True:
        res = coll.get(limit=limit, offset=offset, include=["metadatas"])
        ids = res.get("ids", [])
        metas = res.get("metadatas", [])
        if not ids:
            break
        for i, _id in enumerate(ids):
            mid = str(_id)
            meta = metas[i] if i < len(metas) else {}
            chroma_map[mid] = {"normalized_url": meta.get("normalized_url", ""), "url_hash": meta.get("url_hash", "")}
        offset += len(ids)
        if len(ids) < limit:
            break

    chroma_ids = set(chroma_map.keys())

    # Compare sets
    missing_in_chroma = sorted(list(maria_ids - chroma_ids))
    extra_in_chroma = sorted(list(chroma_ids - maria_ids))

    mismatches = []
    for aid in sorted(maria_ids & chroma_ids):
        mmeta = maria_map.get(aid, {})
        cmeta = chroma_map.get(aid, {})
        # Compare normalized_url and url_hash
        if (mmeta.get("normalized_url", "") or "") != (cmeta.get("normalized_url", "") or "") or (
            (mmeta.get("url_hash", "") or "") != (cmeta.get("url_hash", "") or "")
        ):
            mismatches.append((aid, mmeta, cmeta))

    ok = True
    if len(maria_ids) != chroma_count:
        print(f"COUNT MISMATCH: MariaDB={len(maria_ids)} != Chroma={chroma_count}")
        ok = False

    if missing_in_chroma:
        print(f"ERROR: {len(missing_in_chroma)} MariaDB article ids missing in Chroma (sample 10): {missing_in_chroma[:10]}")
        ok = False

    if extra_in_chroma:
        print(f"ERROR: {len(extra_in_chroma)} Chroma doc ids not present in MariaDB (sample 10): {extra_in_chroma[:10]}")
        ok = False

    if mismatches:
        print(f"METADATA MISMATCHES: {len(mismatches)} entries where normalized_url or url_hash differ (sample 10):")
        for entry in mismatches[:10]:
            aid, mm, cm = entry
            print(f" - id={aid}\n   Maria: normalized={mm.get('normalized_url')!r} url_hash={mm.get('url_hash')!r}\n   Chroma: normalized={cm.get('normalized_url')!r} url_hash={cm.get('url_hash')!r}")
        ok = False

    if ok:
        if metrics is not None:
            try:
                metrics.record_parity_check("ok")
            except Exception:
                pass
        print("OK: MariaDB and Chroma parity checks passed (one-to-one with matching metadata)")
        return 0
    else:
        if metrics is not None:
            try:
                metrics.record_parity_check("mismatch")
            except Exception:
                pass
        print("PARITY CHECK FAILED — see above details")

    # If repair was requested, describe planned actions and optionally perform them
    if args.repair:
        print("\nRepair mode requested")

        # Print a human summary of what we'd do
        planned = []
        if missing_in_chroma:
            planned.append(f"INSERT {len(missing_in_chroma)} missing articles into Chroma")
        if mismatches:
            planned.append(f"UPDATE {len(mismatches)} mismatched metadata entries in Chroma")
        if extra_in_chroma:
            planned.append(f"{len(extra_in_chroma)} Chroma docs have no MariaDB rows (extra)")

        print("Planned actions:")
        for p_line in planned:
            print(f" - {p_line}")

        # Safety: require explicit confirmation to actually change DBs
        if not args.confirm:
            print("\nDry-run only. Add --confirm to actually perform repair operations.")
            if metrics is not None:
                try:
                    metrics.record_parity_repair("dry_run")
                except Exception:
                    pass
            # Non-zero exit to indicate parity still not OK
            return 2

        # Ensure backup dir exists
        backup_dir = os.path.abspath(args.backup_dir)
        os.makedirs(backup_dir, exist_ok=True)

        # Lazy-import helpers we'll use for repair
        try:  # pragma: no cover - depends on runtime environment
            from database.utils.migrated_database_utils import create_database_service as _create_db
            from agents.memory.tools import get_embedding_model as _get_embedding_model
            from agents.memory.tools import _make_chroma_metadata_safe, _ensure_embedding_metadata
        except Exception as e:  # pragma: no cover - runtime environment required
            print(f"ERROR: Could not import repair helpers: {e}", file=sys.stderr)
            return 1

        # Re-open a database service for fetching article content/metadata
        try:
            db_service = _create_db()
            conn = db_service.get_connection()
            cursor = conn.cursor()
        except Exception as e:  # pragma: no cover - runtime environment required
            print(f"ERROR: Could not connect to MariaDB for repair: {e}", file=sys.stderr)
            return 1

        # Backup any Chroma docs that are extra or mismatched before we change anything
        try:
            to_backup = list(set(extra_in_chroma + [mid for (mid, _, _) in mismatches]))
            if to_backup:
                print(f"Backing up {len(to_backup)} existing Chroma docs to {backup_dir}")
                try:
                    docs = []
                    # Try to fetch full docs/metadata/embeddings from chroma using ids
                    try:
                        fetched = coll.get(ids=to_backup, include=["metadatas", "documents", "embeddings"])
                    except Exception:
                        # Fallback: page and filter local chroma_map
                        fetched = {"ids": [], "metadatas": [], "documents": [], "embeddings": []}
                        for _id in to_backup:
                            entry = {"id": _id, "metadata": chroma_map.get(str(_id), {}), "document": None}
                            fetched["ids"].append(_id)

                    ids_f = fetched.get("ids", [])
                    metas_f = fetched.get("metadatas", [])
                    docs_f = fetched.get("documents", [])
                    embs_f = fetched.get("embeddings", [])
                    for idx, _id in enumerate(ids_f):
                        docs.append({
                            "id": str(_id),
                            "metadata": metas_f[idx] if idx < len(metas_f) else {},
                            "document": docs_f[idx] if idx < len(docs_f) else None,
                            "embedding": embs_f[idx] if idx < len(embs_f) else None,
                        })

                    # Use timezone-aware timestamps to avoid deprecation warnings
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    filename = os.path.join(backup_dir, f"verify_chroma_parity_backup_{args.collection}_{stamp}.json")
                    with open(filename, "w", encoding="utf-8") as fh:
                        json.dump({"collection": args.collection, "backup_at": stamp, "docs": docs}, fh, indent=2)

                except Exception as e:
                    print(f"WARNING: Could not backup Chroma docs fully: {e}")

        except Exception:
            # No backup needed
            pass

        # Prepare embedding model if needed
        embedding_model = None
        if not args.skip_embeddings:
            embedding_model = _get_embedding_model()
            if embedding_model is None:
                print("WARNING: embedding model not available; continuing with --skip-embeddings behavior where possible")
                # fall through to skip embeddings if unavailable
                args.skip_embeddings = True

        # Helper to fetch articles from MariaDB by ids
        def fetch_articles(ids: list[str]) -> dict[str, dict]:
            if not ids:
                return {}
            q = f"SELECT id, content, metadata, normalized_url, url_hash, title FROM articles WHERE id IN ({','.join(['%s'] * len(ids))})"
            cursor.execute(q, tuple(ids))
            rows = cursor.fetchall() or []
            out: dict[str, dict] = {}
            for row in rows:
                aid = str(row[0])
                content = row[1] or ""
                metadata_raw = row[2] or "{}"
                try:
                    parsed = json.loads(metadata_raw) if isinstance(metadata_raw, str) else (metadata_raw or {})
                except Exception:
                    parsed = {"raw": str(metadata_raw)}
                parsed.setdefault("normalized_url", row[3] or parsed.get("normalized_url", ""))
                parsed.setdefault("url_hash", row[4] or parsed.get("url_hash", ""))
                parsed.setdefault("title", row[5] or parsed.get("title", ""))
                out[aid] = {"content": content, "metadata": parsed}
            return out

        # Perform repairs: insert missing & update mismatches
        success_inserts = 0
        success_updates = 0
        failed_ops = 0

        try:
            # Missing => insert using upsert
            if missing_in_chroma:
                print(f"Fetching {len(missing_in_chroma)} missing articles from MariaDB")
                batch = list(missing_in_chroma)
                articles = fetch_articles(batch)
                for aid in batch:
                    art = articles.get(aid)
                    if not art:
                        print(f"WARNING: Missing MariaDB row for id {aid}, skipping")
                        failed_ops += 1
                        continue
                    content = art.get("content", "")
                    metadata = art.get("metadata", {})
                    chroma_meta = _make_chroma_metadata_safe(_ensure_embedding_metadata(metadata or {}))
                    try:
                        embedding_list = None
                        if not args.skip_embeddings and embedding_model is not None:
                            emb = embedding_model.encode(content)
                            embedding_list = list(map(float, emb)) if emb is not None else None

                        # Build upsert args
                        up_args = {"ids": [str(aid)], "metadatas": [chroma_meta], "documents": [content]}
                        if embedding_list is not None:
                            up_args["embeddings"] = [embedding_list]

                        coll.upsert(**up_args)
                        success_inserts += 1
                        if logger:
                            logger.info("Upserted missing Chroma id %s", aid)
                        if metrics is not None:
                            try:
                                metrics.record_parity_repair("inserted")
                            except Exception:
                                pass
                        print(f"Inserted/upserted missing Chroma id {aid}")
                    except Exception as e:
                        failed_ops += 1
                        if metrics is not None:
                            try:
                                metrics.record_parity_repair("failed")
                            except Exception:
                                pass
                        print(f"ERROR: Failed to upsert id {aid} into Chroma: {e}")

            # Mismatches => update metadata and content (recompute embedding optionally)
            if mismatches:
                update_ids = [m[0] for m in mismatches]
                print(f"Updating {len(update_ids)} mismatched docs in Chroma")
                articles = fetch_articles(update_ids)
                for aid in update_ids:
                    art = articles.get(aid)
                    if not art:
                        print(f"WARNING: Missing MariaDB row for id {aid} while updating mismatch; skipping")
                        failed_ops += 1
                        continue
                    content = art.get("content", "")
                    metadata = art.get("metadata", {})
                    chroma_meta = _make_chroma_metadata_safe(_ensure_embedding_metadata(metadata or {}))
                    try:
                        embedding_list = None
                        if not args.skip_embeddings and embedding_model is not None:
                            emb = embedding_model.encode(content)
                            embedding_list = list(map(float, emb)) if emb is not None else None

                        up_args = {"ids": [str(aid)], "metadatas": [chroma_meta], "documents": [content]}
                        if embedding_list is not None:
                            up_args["embeddings"] = [embedding_list]

                        coll.upsert(**up_args)
                        success_updates += 1
                        if logger:
                            logger.info("Updated mismatched Chroma id %s", aid)
                        if metrics is not None:
                            try:
                                metrics.record_parity_repair("updated")
                            except Exception:
                                pass
                    except Exception as e:
                        failed_ops += 1
                        if metrics is not None:
                            try:
                                metrics.record_parity_repair("failed")
                            except Exception:
                                pass
                        print(f"ERROR: Failed to update Chroma id {aid}: {e}")

            # Extra docs - optionally delete
            deleted = 0
            if extra_in_chroma and args.delete_extras:
                try:
                    print(f"Deleting {len(extra_in_chroma)} extra Chroma docs as requested")
                    coll.delete(ids=extra_in_chroma)
                    deleted = len(extra_in_chroma)
                    if metrics is not None:
                        try:
                            metrics.record_parity_repair("deleted")
                        except Exception:
                            pass
                except Exception as e:
                    failed_ops += len(extra_in_chroma)
                    if metrics is not None:
                        try:
                            metrics.record_parity_repair("failed")
                        except Exception:
                            pass
                    print(f"ERROR: Failed to delete extras: {e}")

        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        print("\nRepair results:")
        print(f" - inserted/upserted: {success_inserts}")
        print(f" - updated mismatches: {success_updates}")
        if deleted:
            print(f" - deleted extras: {deleted}")
        if failed_ops:
            print(f" - failed ops: {failed_ops}")

        if failed_ops:
            if metrics is not None:
                try:
                    metrics.record_parity_repair("repair_partial_failure")
                except Exception:
                    pass
            print("REPAIR COMPLETE: some operations failed; inspect logs")
            return 3
        else:
            if metrics is not None:
                try:
                    metrics.record_parity_repair("repair_success")
                except Exception:
                    pass
            print("REPAIR COMPLETE: all requested repairs applied successfully")
            return 0

    # No repair requested and parity failed
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
