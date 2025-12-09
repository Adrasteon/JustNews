#!/usr/bin/env python3
"""Seed the `sources` table from a file (markdown or plaintext).

Idempotent behaviour:
- If the `sources` table is absent or empty, the script will populate it.
- When invoked with --force the script will DELETE FROM sources and re-seed
  from the canonical list.
- The script supports --dry-run to preview changes without committing.

This script prefers environment variables in this order:
 - JUSTNEWS_DB_* (used by deploy/start scripts)
 - MARIADB_* (used elsewhere in the codebase)

Example:
  scripts/news_outlets.py --file scripts/ops/markdown_docs/agent_documentation/potential_news_sources.md --force

"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Iterable, List

try:  # prefer mysql-connector installed in the dev env
    import mysql.connector
except Exception:  # pragma: no cover - defensive
    mysql = None


DOMAIN_RE = re.compile(r"([a-z0-9-]+\.)+[a-z]{2,}", re.I)


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name) or os.environ.get(name.lower(), default)


def db_config_from_env() -> dict:
    # Mirror start_services_daemon.sh environment variables
    host = _env("JUSTNEWS_DB_HOST") or _env("MARIADB_HOST") or "localhost"
    port = int(_env("JUSTNEWS_DB_PORT") or _env("MARIADB_PORT") or 3306)
    user = _env("JUSTNEWS_DB_USER") or _env("MARIADB_USER") or "justnews"
    password = _env("JUSTNEWS_DB_PASSWORD") or _env("MARIADB_PASSWORD") or ""
    database = _env("JUSTNEWS_DB_NAME") or _env("MARIADB_DB") or "justnews"
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "use_pure": True,
    }


def parse_domains_from_text(text: str) -> List[str]:
    """Extract plausible hostnames/domains from arbitrary text.

    This function is intentionally permissive: it will extract tokens that
    look like domains and de-duplicate them while preserving order.
    """
    seen = set()
    result: List[str] = []
    for m in DOMAIN_RE.finditer(text):
        domain = m.group(0).lower().strip().lstrip(".")
        # Normalise common www. prefix by removing it since we want bare domains
        if domain.startswith("www."):
            domain = domain[4:]
        # remove trivial oddities
        if domain.endswith("."):
            domain = domain[:-1]
        # Skip common source code / documentation file extensions that accidentally match
        ext = domain.split('.')[-1]
        if ext in ('py', 'md', 'sh', 'txt', 'json', 'yml', 'yaml', 'html', 'js', 'css', 'ts', 'xml'):
            continue

        if domain not in seen:
            seen.add(domain)
            result.append(domain)
    return result


def read_input_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def connect_db():
    if mysql is None:
        raise RuntimeError("mysql.connector not available; install mysql-connector-python")
    cfg = db_config_from_env()
    return mysql.connector.connect(**cfg)


def ensure_sources_table(conn) -> None:
    # Minimal DDL to ensure sources table exists with a few useful columns.
    ddl = """
    CREATE TABLE IF NOT EXISTS sources (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      domain VARCHAR(255) UNIQUE,
      name VARCHAR(255),
      url VARCHAR(1024),
      metadata JSON DEFAULT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """
    cur = conn.cursor()
    try:
        cur.execute(ddl)
        conn.commit()
    finally:
        cur.close()


def get_sources_count(conn) -> int:
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM sources")
        r = cur.fetchone()
        return int(r[0]) if r else 0
    finally:
        cur.close()


def delete_all_sources(conn) -> None:
    # Deleting all sources can violate foreign key constraints (articles.source_id)
    # so use a safer approach elsewhere; keep this helper for legacy/hard-delete
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM sources")
        conn.commit()
    finally:
        cur.close()


def get_existing_domains(conn) -> set[str]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT domain FROM sources")
        rows = cur.fetchall() or []
        return {r[0].lower() for r in rows if r and r[0]}
    finally:
        cur.close()


def archive_unlisted_domains(conn, keep_domains: set[str]) -> int:
    """Mark domains that are not in keep_domains as archived in metadata.

    Returns the number of rows updated.
    """
    cur = conn.cursor()
    try:
        # Build a SQL predicate to find domains not in the keep list
        if not keep_domains:
            return 0
        placeholders = ", ".join(["%s"] * len(keep_domains))
        sql = (
            "UPDATE sources SET metadata = JSON_SET(COALESCE(metadata, JSON_OBJECT()), '$.archived', true)"
            " WHERE LOWER(domain) NOT IN (" + placeholders + ")"
        )
        cur.execute(sql, tuple(keep_domains))
        count = cur.rowcount
        conn.commit()
        return count
    finally:
        cur.close()


def insert_domains(conn, domains: Iterable[str]) -> int:
    cur = conn.cursor()
    try:
        count = 0
        for d in domains:
            try:
                cur.execute(
                    "INSERT INTO sources(domain, name, url) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name), url=VALUES(url)",
                    (d, d, f"https://{d}"),
                )
                count += 1
            except Exception as exc:  # pragma: no cover - DB insert guard
                print(f"WARNING: could not insert {d}: {exc}", file=sys.stderr)
        conn.commit()
        return count
    finally:
        cur.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed or re-seed the JustNews sources table from a file")
    parser.add_argument("--file", "-f", required=True, help="Markdown or text file containing candidate domains")
    parser.add_argument("--force", action="store_true", help="Flush existing sources and re-seed the canonical list")
    parser.add_argument("--dry-run", action="store_true", help="Parse and show what would be seeded without connecting to DB")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of domains to load (0=all)")

    args = parser.parse_args(argv)

    if args.dry_run:
        content = read_input_file(args.file)
        domains = parse_domains_from_text(content)
        if args.limit > 0:
            domains = domains[: args.limit]
        print("Found domains to seed (dry-run):")
        for d in domains:
            print(f" - {d}")
        return 0

    # Connect to DB and perform idempotent seeding
    conn = None
    try:
        conn = connect_db()
        ensure_sources_table(conn)
        current_count = get_sources_count(conn)
        if current_count > 0 and not args.force:
            print(f"Aborting: sources table already populated ({current_count} rows). Use --force to replace.")
            return 0

        if args.force and current_count > 0:
            print(f"Forcing seeding: will upsert canonical domains and archive any unlisted existing sources (was {current_count} rows)...")
            # Upsert will be performed below. We'll mark any existing domains not present
            # in the canonical list as archived so we don't break referential integrity.

        content = read_input_file(args.file)
        domains = parse_domains_from_text(content)
        if args.limit > 0:
            domains = domains[: args.limit]
        # Normalise to lower-case bare domains for consistency
        domains = [d.lower().lstrip("www.") for d in domains]
        print(f"Seeding {len(domains)} domains into sources table")
        inserted = insert_domains(conn, domains)
        print(f"Inserted/updated {inserted} rows")

        # Archive any existing domains that are not present in the canonical list
        try:
            archived = archive_unlisted_domains(conn, set(domains))
            if archived:
                print(f"Archived {archived} previously-existing domains not in canonical set")
            else:
                print("No unlisted domains required archiving")
        except Exception:
            # Best-effort; don't fail the whole job if archiving isn't supported by DB
            print("Warning: failed to archive unlisted domains (DB error)")
    except Exception as exc:  # pragma: no cover - top-level guard
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
