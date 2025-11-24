#!/usr/bin/env python3
"""
Database Flush Script - Clear Article Data While Preserving Sources

This script safely clears all article-related data from MariaDB and ChromaDB
while preserving the sources table which contains legitimate source information.

WARNING: This operation is destructive and cannot be undone!
Make sure you have backups before running this script.

Usage:
    python3 flush_article_data.py [--confirm]
"""

import argparse
import sys

import chromadb

from database.utils.migrated_database_utils import create_database_service


def get_confirmation() -> bool:
    """Get user confirmation for destructive operation"""
    print("=" * 60)
    print("⚠️  DANGER: This will permanently delete article data!")
    print("=" * 60)
    print("This script will:")
    print("✅ KEEP: sources table (366 records)")
    print("🗑️  DELETE: articles table (4,721 records)")
    print("🗑️  DELETE: article_source_map table (606 records)")
    print("🗑️  DELETE: crawler_performance table (0 records)")
    print("🗑️  DELETE: ChromaDB articles collection (4,069 documents)")
    print()
    print("After this, you will have a clean slate for proper article ingestion.")
    print("=" * 60)

    response = input("Type 'YES' to confirm deletion: ").strip()
    return response == "YES"


def clear_mariadb_data(db_service) -> list[str]:
    """Clear article-related tables from MariaDB, preserving sources"""
    cursor = db_service.mb_conn.cursor()
    operations = []

    try:
        # Disable foreign key checks temporarily
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        # Clear article-related tables
        tables_to_clear = ['crawler_performance', 'article_source_map', 'articles']

        for table in tables_to_clear:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]

            cursor.execute(f"TRUNCATE TABLE {table}")
            operations.append(f"Truncated {table}: {count} records deleted")

        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        db_service.mb_conn.commit()
        cursor.close()

        return operations

    except Exception as e:
        db_service.mb_conn.rollback()
        cursor.close()
        raise Exception(f"MariaDB clear failed: {e}") from e


def clear_chromadb_data() -> list[str]:
    """Clear the articles collection from ChromaDB"""
    operations = []

    try:
        client = chromadb.HttpClient(host='localhost', port=3307)

        # Get current count
        collection = client.get_collection('articles')
        count = collection.count()
        operations.append(f"ChromaDB articles collection had {count} documents")

        # Delete the collection
        client.delete_collection('articles')
        operations.append("Deleted ChromaDB articles collection")

        # Recreate empty collection with same configuration
        collection = client.create_collection(
            name='articles',
            metadata={"hnsw:space": "cosine"}
        )
        operations.append("Recreated empty ChromaDB articles collection")

        return operations

    except Exception as e:
        raise Exception(f"ChromaDB clear failed: {e}") from e


def verify_cleanup(db_service) -> list[str]:
    """Verify that the cleanup was successful"""
    cursor = db_service.mb_conn.cursor()
    verifications = []

    try:
        # Check MariaDB tables
        tables_to_check = ['articles', 'article_source_map', 'crawler_performance']
        for table in tables_to_check:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            verifications.append(f"{table}: {count} records (should be 0)")

        # Check sources table is preserved
        cursor.execute("SELECT COUNT(*) FROM sources")
        sources_count = cursor.fetchone()[0]
        verifications.append(f"sources: {sources_count} records (should be 366)")

        cursor.close()

        # Check ChromaDB
        client = chromadb.HttpClient(host='localhost', port=3307)
        collection = client.get_collection('articles')
        chromadb_count = collection.count()
        verifications.append(f"ChromaDB articles: {chromadb_count} documents (should be 0)")

        return verifications

    except Exception as e:
        cursor.close()
        raise Exception(f"Verification failed: {e}") from e


def main():
    parser = argparse.ArgumentParser(description="Flush article data while preserving sources")
    parser.add_argument("--confirm", action="store_true",
                       help="Skip confirmation prompt (use with caution!)")
    args = parser.parse_args()

    print("🧹 JustNews Database Flush Script")
    print("=================================")

    # Get confirmation unless --confirm flag is used
    if not args.confirm and not get_confirmation():
        print("❌ Operation cancelled by user.")
        sys.exit(0)

    try:
        # Initialize database service
        print("🔌 Connecting to databases...")
        db_service = create_database_service()

        # Clear MariaDB data
        print("🗑️  Clearing MariaDB article data...")
        mariadb_ops = clear_mariadb_data(db_service)
        for op in mariadb_ops:
            print(f"   {op}")

        # Clear ChromaDB data
        print("🗑️  Clearing ChromaDB article data...")
        chromadb_ops = clear_chromadb_data()
        for op in chromadb_ops:
            print(f"   {op}")

        # Verify cleanup
        print("✅ Verifying cleanup...")
        verifications = verify_cleanup(db_service)
        for verification in verifications:
            print(f"   {verification}")

        # Close connections
        db_service.close()

        print()
        print("🎉 Database flush completed successfully!")
        print("📝 Summary:")
        print("   - Article data cleared from MariaDB and ChromaDB")
        print("   - Sources table preserved (366 records)")
        print("   - Ready for fresh article ingestion with improved crawler")

    except Exception as e:
        print(f"❌ Error during database flush: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
