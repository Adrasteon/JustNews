#!/usr/bin/env python3
"""
Database Verification Script
Check MariaDB and ChromaDB for article ingestion and embedding correctness
"""

import sys
from pathlib import Path

import chromadb

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def check_mariadb():
    """Check MariaDB for ingested articles"""
    print("🔍 Checking MariaDB...")

    try:
        # Use migrated database utilities for proper connection
        from database.utils.migrated_database_utils import (
            create_database_service,
            get_database_stats,
        )

        service = create_database_service()
        stats = get_database_stats(service)

        article_count = stats.get('mariadb', {}).get('articles', 0)
        source_count = stats.get('mariadb', {}).get('sources', 0)

        print(f"📊 Articles in MariaDB: {article_count}")
        print(f"📰 Sources in MariaDB: {source_count}")

        if article_count > 0:
            # Get recent articles using the service
            recent_articles = service.get_recent_articles(limit=5)

            print("\n📝 Recent Articles:")
            for article in recent_articles:
                article_id = article.get('id')
                title = article.get('title', 'N/A')
                url = article.get('url', 'N/A')
                created_at = article.get('created_at')
                analyzed = article.get('analyzed', False)
                status = "✅ Analyzed" if analyzed else "⏳ Pending"
                print(f"  ID: {article_id}")
                print(f"  Title: {title[:80]}{'...' if len(title) > 80 else ''}")
                print(f"  URL: {url}")
                print(f"  Created: {created_at}")
                print(f"  Status: {status}")
                print()

            # Get source stats using direct query
            cursor = service.mb_conn.cursor()
            cursor.execute("""
                SELECT s.domain, COUNT(a.id) as article_count
                FROM sources s
                LEFT JOIN articles a ON s.id = a.source_id
                GROUP BY s.id, s.domain
                ORDER BY article_count DESC
                LIMIT 10
            """)
            source_stats = cursor.fetchall()
            cursor.close()

            print("\n📈 Articles by Source:")
            for domain, count in source_stats:
                print(f"  {domain}: {count} articles")

        service.close()
        return article_count

    except Exception as e:
        print(f"❌ MariaDB Error: {e}")
        return 0

def check_chromadb():
    """Check ChromaDB for embeddings"""
    print("\n🔍 Checking ChromaDB...")

    try:
        # Connect to ChromaDB (server mode)
        client = chromadb.HttpClient(host="localhost", port=3307)

        # List collections
        collections = client.list_collections()
        print(f"📚 ChromaDB Collections: {len(collections)}")

        for collection in collections:
            print(f"\n📖 Collection: {collection.name}")

            # Get collection info
            coll = client.get_collection(collection.name)
            count = coll.count()
            print(f"  Documents: {count}")

            if count > 0:
                # Get sample embeddings
                results = coll.get(limit=3, include=['metadatas', 'documents'])

                print("  Sample Documents:")
                for i, (doc_id, metadata, document) in enumerate(zip(
                    results['ids'],
                    results['metadatas'],
                    results['documents']
                )):
                    print(f"    Document {i+1}:")
                    print(f"      ID: {doc_id}")
                    print(f"      Title: {metadata.get('title', 'N/A')[:60]}{'...' if len(metadata.get('title', '')) > 60 else ''}")
                    print(f"      URL: {metadata.get('url', 'N/A')}")
                    print(f"      Content preview: {document[:100] if document else 'N/A'}...")
                    print()

        return len(collections), sum(coll.count() for coll in [client.get_collection(c.name) for c in collections])

    except Exception as e:
        print(f"❌ ChromaDB Error: {e}")
        return 0, 0

def cross_check_databases(mariadb_count, chroma_collections, chroma_docs):
    """Cross-check data between databases"""
    print("\n🔗 Cross-Database Verification:")

    if mariadb_count == chroma_docs:
        print("✅ Article counts match between MariaDB and ChromaDB")
    else:
        print(f"⚠️  Count mismatch: MariaDB={mariadb_count}, ChromaDB={chroma_docs}")

    if chroma_collections > 0:
        print("✅ ChromaDB collections exist")
    else:
        print("❌ No ChromaDB collections found")

    # Overall assessment
    print("\n🎯 Overall Assessment:")
    if mariadb_count > 0 and chroma_docs > 0:
        success_rate = min(mariadb_count, chroma_docs) / max(mariadb_count, chroma_docs)
        if success_rate > 0.9:
            print("🎉 SUCCESS: Both databases populated correctly!")
        elif success_rate > 0.7:
            print("⚠️  PARTIAL: Most data ingested successfully")
        else:
            print("❌ ISSUES: Significant data ingestion problems")
    else:
        print("❌ FAILURE: One or both databases empty")

def main():
    """Main verification function"""
    print("🚀 JustNews Database Verification")
    print("=" * 50)

    # Check MariaDB
    mariadb_count = check_mariadb()

    # Check ChromaDB
    chroma_collections, chroma_docs = check_chromadb()

    # Cross-check
    cross_check_databases(mariadb_count, chroma_collections, chroma_docs)

    print("\n✨ Verification Complete!")

if __name__ == "__main__":
    main()
