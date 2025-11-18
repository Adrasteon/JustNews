#!/usr/bin/env python3
"""
Database Backup Script - Backup Article Data Before Flushing

Creates backups of article-related data before the flush operation.

Usage:
    python3 backup_article_data.py
"""

import json
from datetime import datetime
from pathlib import Path

import chromadb

from database.utils.migrated_database_utils import create_database_service


def backup_mariadb_data(db_service, backup_dir: Path):
    """Backup article-related tables from MariaDB"""
    cursor = db_service.mb_conn.cursor(dictionary=True)

    tables_to_backup = ['articles', 'article_source_map', 'crawler_performance']

    for table in tables_to_backup:
        print(f"📦 Backing up {table}...")

        # Get all data
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()

        # Save to JSON
        backup_file = backup_dir / f"{table}_backup.json"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=2, default=str, ensure_ascii=False)

        print(f"   Saved {len(rows)} records to {backup_file}")

    cursor.close()


def backup_chromadb_data(backup_dir: Path):
    """Backup ChromaDB articles collection"""
    print("📦 Backing up ChromaDB articles collection...")

    client = chromadb.HttpClient(host='localhost', port=3307)
    collection = client.get_collection('articles')

    # Get all data
    result = collection.get(include=['documents', 'metadatas', 'embeddings'])

    # Save to JSON
    backup_data = {
        'ids': result['ids'],
        'documents': result['documents'],
        'metadatas': result['metadatas'],
        'embeddings': result['embeddings']
    }

    backup_file = backup_dir / "chromadb_articles_backup.json"
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=2, default=str, ensure_ascii=False)

    print(f"   Saved {len(result['ids'])} documents to {backup_file}")


def main():
    print("💾 JustNews Database Backup Script")
    print("===================================")

    # Create backup directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"./database_backups/backup_{timestamp}")
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"📁 Backup directory: {backup_dir}")

    try:
        # Initialize database service
        print("🔌 Connecting to databases...")
        db_service = create_database_service()

        # Backup MariaDB data
        backup_mariadb_data(db_service, backup_dir)

        # Backup ChromaDB data
        backup_chromadb_data(backup_dir)

        # Close connections
        db_service.close()

        print()
        print("✅ Database backup completed successfully!")
        print(f"📂 Backup location: {backup_dir}")
        print("💡 You can now safely run the flush script if needed.")

    except Exception as e:
        print(f"❌ Error during database backup: {e}")
        exit(1)


if __name__ == "__main__":
    main()
