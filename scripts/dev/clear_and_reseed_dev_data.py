#!/usr/bin/env python3
"""
Clear development article data (MariaDB + ChromaDB) and reseed the minimal articles table.

This wrapper calls the existing flush and seeder helpers to produce a single
convenient point to reset the article ingestion dataset in a development environment.

Usage:
    python3 scripts/dev/clear_and_reseed_dev_data.py [--confirm] [--skip-chroma] [--seed-articles] [--seed-sources] [--sources-file PATH]

Notes:
 - This is destructive: it will TRUNCATE article-related tables and delete the Chroma
   'articles' collection. Only run this in development environments where data can be lost.
 - The script will NOT reseed anything by default. Use --seed-articles to reseed
     a minimal articles schema, or --seed-sources to repopulate the `sources` table.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from database.utils.migrated_database_utils import create_database_service


def get_confirmation() -> bool:
    print("\n=== DEStructive Dev DB Reset ===\n")
    print("This will TRUNCATE article tables in MariaDB and DELETE the ChromaDB 'articles' collection.")
    print("Only run on dev envs where you don't need to keep existing data.")
    resp = input("Type 'YES' to continue: ").strip()
    return resp == "YES"


def run_clear_and_reseed(skip_chroma: bool = False, seed_articles: bool = False, seed_sources: bool = False, sources_file: str | None = None) -> None:
    # Create a database service instance (migrated) and run the clear operations
    db_service = create_database_service()

    # Import flush functions lazily so this module can be imported safely in CI without executing
    # destructive operations.
    from flush_article_data import clear_mariadb_data, clear_chromadb_data, verify_cleanup

    print("Connecting to DB service and clearing MariaDB article tables...")
    try:
        ops = clear_mariadb_data(db_service)
        for op in ops:
            print(f"  - {op}")
    except Exception as e:
        print(f"ERROR: failed to clear MariaDB data: {e}")
        db_service.close()
        raise

    if not skip_chroma:
        print("Clearing ChromaDB 'articles' collection...")
        try:
            chroma_ops = clear_chromadb_data()
            for op in chroma_ops:
                print(f"  - {op}")
        except Exception as e:
            print(f"ERROR: failed to clear ChromaDB: {e}")
            # continue — allow verify to run

    print("Verifying cleanup...")
    try:
        ver = verify_cleanup(db_service)
        for v in ver:
            print(f"  - {v}")
    except Exception as e:
        print(f"WARNING: verification failed: {e}")

    # Optionally reseed things after the wipe. We provide two separate operations:
    #  - seed_articles: create minimal articles schema and a sample article (keeps existing behaviour)
    #  - seed_sources: populate the `sources` table using scripts/news_outlets.py (ONLY sources)
    # The default behaviour is NOT to reseed anything unless explicitly requested.
    if seed_articles:
        print("Reseeding minimal articles schema & sample row (editorial harness)...")
        try:
            import importlib.util

            bootstrap_file = Path(__file__).resolve().parent / "bootstrap_editorial_harness_db.py"
            spec = importlib.util.spec_from_file_location("bootstrap_editorial_harness_db", str(bootstrap_file))
            bootstrap = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(bootstrap)  # type: ignore[attr-defined]

            if hasattr(bootstrap, "main"):
                bootstrap.main()
            else:
                conn = bootstrap.build_connection()
                try:
                    bootstrap.ensure_schema(conn)
                    bootstrap.seed_sample_row(conn)
                finally:
                    conn.close()

            print("Article reseed complete.")
        except Exception as e:
            print(f"ERROR: article reseeding failed: {e}")

    if seed_sources:
        print("Reseeding sources table (only source URLs) — no articles will be seeded...")
        # Determine candidate file path for source list
        default_sources = Path(__file__).resolve().parent.parent / "ops" / "markdown_docs" / "agent_documentation" / "potential_news_sources.md"
        sources_path = None
        if sources_file:
            sources_path = Path(sources_file)
        elif default_sources.exists():
            sources_path = default_sources

        if not sources_path or not sources_path.exists():
            raise RuntimeError("No sources file available — pass --sources-file <path> to specify a domain list to seed")

        # load and run scripts/news_outlets.py by path, prefering to call its main() fn
        try:
            import importlib.util

            seeder_file = Path(__file__).resolve().parent.parent / "news_outlets.py"
            spec = importlib.util.spec_from_file_location("news_outlets", str(seeder_file))
            seeder = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(seeder)  # type: ignore[attr-defined]

            # news_outlets.main expects argv-style list and requires --file
            seeder.main(["--file", str(sources_path), "--force"])  # type: ignore[arg-type]
            print("Sources reseed complete.")
        except Exception as e:
            print(f"ERROR: failed to reseed sources: {e}")

    # Close db service
    try:
        db_service.close()
    except Exception:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear dev article data and optionally reseed sources or a minimal article sample")
    parser.add_argument("--confirm", action="store_true", help="Skip interactive confirmation")
    parser.add_argument("--skip-chroma", action="store_true", help="Skip clearing ChromaDB (only clear MariaDB)")
    parser.add_argument("--seed-articles", action="store_true", help="Reseed a minimal articles schema and sample article (editorial harness)")
    parser.add_argument("--seed-sources", action="store_true", help="Repopulate the `sources` table only using scripts/news_outlets.py")
    parser.add_argument("--sources-file", type=str, help="Path to a markdown/text file containing candidate domains to seed (overrides default) ")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.confirm and not get_confirmation():
        print("Aborting — no changes made.")
        sys.exit(0)

    run_clear_and_reseed(skip_chroma=args.skip_chroma, seed_articles=args.seed_articles, seed_sources=args.seed_sources, sources_file=args.sources_file)


if __name__ == "__main__":
    main()
