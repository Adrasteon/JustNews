"""
Migrated Database Models - MariaDB + ChromaDB Integration
Models for the migrated JustNews database schema

Features:
- MariaDB models for relational data (articles, sources, mappings)
- ChromaDB integration for vector embeddings
- Semantic search capabilities
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import json
import mysql.connector
import chromadb
from sentence_transformers import SentenceTransformer

from common.observability import get_logger

logger = get_logger(__name__)


class Source:
    """Source model for MariaDB"""

    __tablename__ = "sources"

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.url = kwargs.get('url')
        self.domain = kwargs.get('domain')
        self.name = kwargs.get('name')
        self.description = kwargs.get('description')
        self.country = kwargs.get('country')
        self.language = kwargs.get('language')
        self.paywall = kwargs.get('paywall', False)
        self.paywall_type = kwargs.get('paywall_type')
        self.last_verified = kwargs.get('last_verified')
        self.metadata = kwargs.get('metadata', {})
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')

    @classmethod
    def from_row(cls, row) -> 'Source':
        """Create Source from database row"""
        return cls(
            id=row[0],
            url=row[1],
            domain=row[2],
            name=row[3],
            description=row[4],
            country=row[5],
            language=row[6],
            paywall=row[7],
            paywall_type=row[8],
            last_verified=row[9],
            metadata=json.loads(row[10]) if row[10] else {},
            created_at=row[11],
            updated_at=row[12]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'url': self.url,
            'domain': self.domain,
            'name': self.name,
            'description': self.description,
            'country': self.country,
            'language': self.language,
            'paywall': self.paywall,
            'paywall_type': self.paywall_type,
            'last_verified': self.last_verified,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class Article:
    """Article model for MariaDB"""

    __tablename__ = "articles"

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.url = kwargs.get('url')
        self.title = kwargs.get('title')
        self.content = kwargs.get('content')
        self.summary = kwargs.get('summary')
        self.analyzed = kwargs.get('analyzed', False)
        self.source_id = kwargs.get('source_id')
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')
        self.normalized_url = kwargs.get('normalized_url')
        self.url_hash = kwargs.get('url_hash')
        self.url_hash_algo = kwargs.get('url_hash_algo', 'sha256')
        self.language = kwargs.get('language')
        self.section = kwargs.get('section')
        self.tags = kwargs.get('tags', [])
        self.authors = kwargs.get('authors', [])
        self.raw_html_ref = kwargs.get('raw_html_ref')
        self.extraction_confidence = kwargs.get('extraction_confidence')
        self.needs_review = kwargs.get('needs_review', False)
        self.review_reasons = kwargs.get('review_reasons', [])
        self.extraction_metadata = kwargs.get('extraction_metadata', {})
        self.structured_metadata = kwargs.get('structured_metadata', {})
        self.publication_date = kwargs.get('publication_date')
        self.metadata = kwargs.get('metadata', {})
        self.collection_timestamp = kwargs.get('collection_timestamp')

    @classmethod
    def from_row(cls, row) -> 'Article':
        """Create Article from database row"""
        return cls(
            id=row[0],
            url=row[1],
            title=row[2],
            content=row[3],
            summary=row[4],
            analyzed=row[5],
            source_id=row[6],
            created_at=row[7],
            updated_at=row[8],
            normalized_url=row[9],
            url_hash=row[10],
            url_hash_algo=row[11],
            language=row[12],
            section=row[13],
            tags=json.loads(row[14]) if row[14] else [],
            authors=json.loads(row[15]) if row[15] else [],
            raw_html_ref=row[16],
            extraction_confidence=row[17],
            needs_review=row[18],
            review_reasons=json.loads(row[19]) if row[19] else [],
            extraction_metadata=json.loads(row[20]) if row[20] else {},
            structured_metadata=json.loads(row[21]) if row[21] else {},
            publication_date=row[22],
            metadata=json.loads(row[23]) if row[23] else {},
            collection_timestamp=row[24]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'content': self.content,
            'summary': self.summary,
            'analyzed': self.analyzed,
            'source_id': self.source_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'normalized_url': self.normalized_url,
            'url_hash': self.url_hash,
            'url_hash_algo': self.url_hash_algo,
            'language': self.language,
            'section': self.section,
            'tags': self.tags,
            'authors': self.authors,
            'raw_html_ref': self.raw_html_ref,
            'extraction_confidence': self.extraction_confidence,
            'needs_review': self.needs_review,
            'review_reasons': self.review_reasons,
            'extraction_metadata': self.extraction_metadata,
            'structured_metadata': self.structured_metadata,
            'publication_date': self.publication_date,
            'metadata': self.metadata,
            'collection_timestamp': self.collection_timestamp
        }


class ArticleSourceMap:
    """Article-Source mapping model for MariaDB"""

    __tablename__ = "article_source_map"

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.article_id = kwargs.get('article_id')
        self.source_id = kwargs.get('source_id')
        self.confidence = kwargs.get('confidence', 1.0)
        self.detected_at = kwargs.get('detected_at')
        self.metadata = kwargs.get('metadata', {})

    @classmethod
    def from_row(cls, row) -> 'ArticleSourceMap':
        """Create ArticleSourceMap from database row"""
        return cls(
            id=row[0],
            article_id=row[1],
            source_id=row[2],
            confidence=row[3],
            detected_at=row[4],
            metadata=json.loads(row[5]) if row[5] else {}
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'article_id': self.article_id,
            'source_id': self.source_id,
            'confidence': self.confidence,
            'detected_at': self.detected_at,
            'metadata': self.metadata
        }


class MigratedDatabaseService:
    """Service for interacting with the migrated database (MariaDB + ChromaDB)"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mb_conn = None
        self.chroma_client = None
        self.embedding_model = None
        self.collection = None

        self._connect_databases()

    def _connect_databases(self):
        """Connect to MariaDB and ChromaDB"""
        # MariaDB connection
        mb_config = self.config['database']['mariadb']
        self.mb_conn = mysql.connector.connect(
            host=mb_config['host'],
            port=mb_config['port'],
            user=mb_config['user'],
            password=mb_config['password'],
            database=mb_config['database'],
            autocommit=False,
            use_pure=True
        )
        logger.info("Connected to MariaDB")

        # ChromaDB connection
        chroma_config = self.config['database']['chromadb']
        # Use HttpClient with basic settings
        import os
        os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"
        
        # Monkey patch to avoid authentication issues
        from chromadb.api import UserIdentity
        original_get_user_identity = chromadb.api.client.Client.get_user_identity
        
        def patched_get_user_identity(self):
            return UserIdentity(user_id="anonymous", tenant="default", databases=["default"])
        
        # Apply the monkey patch before creating client
        chromadb.api.client.Client.get_user_identity = patched_get_user_identity
        
        try:
            self.chroma_client = chromadb.HttpClient(
                host=chroma_config['host'],
                port=chroma_config['port']
            )
        finally:
            # Restore the original method
            chromadb.api.client.Client.get_user_identity = original_get_user_identity
        
        # Create collection if it doesn't exist
        collection_name = chroma_config['collection']
        try:
            self.collection = self.chroma_client.get_collection(collection_name)
            logger.info(f"Connected to existing ChromaDB collection: {collection_name}")
        except Exception as e:
            logger.info(f"Collection {collection_name} doesn't exist, creating it: {e}")
            self.collection = self.chroma_client.create_collection(
                name=collection_name,
                metadata={"description": "Article embeddings for semantic search"}
            )
            logger.info(f"Created new ChromaDB collection: {collection_name}")
        
        logger.info("Connected to ChromaDB")

        # Embedding model
        embedding_config = self.config['database']['embedding']
        self.embedding_model = SentenceTransformer(embedding_config['model'])
        logger.info(f"Loaded embedding model: {embedding_config['model']}")

    def close(self):
        """Close database connections"""
        if self.mb_conn:
            self.mb_conn.close()
        # ChromaDB client doesn't need explicit closing

    def get_article_by_id(self, article_id: Union[int, str]) -> Optional[Article]:
        """Get article by ID from MariaDB"""
        try:
            cursor = self.mb_conn.cursor()
            query = """
            SELECT id, url, title, content, summary, analyzed, source_id,
                   created_at, updated_at, normalized_url, url_hash, url_hash_algo,
                   language, section, tags, authors, raw_html_ref, extraction_confidence,
                   needs_review, review_reasons, extraction_metadata, structured_metadata,
                   publication_date, metadata, collection_timestamp
            FROM articles WHERE id = %s
            """
            cursor.execute(query, (article_id,))
            row = cursor.fetchone()
            cursor.close()

            if row:
                return Article.from_row(row)
            return None

        except Exception as e:
            logger.error(f"Failed to get article {article_id}: {e}")
            return None

    def get_source_by_id(self, source_id: Union[int, str]) -> Optional[Source]:
        """Get source by ID from MariaDB"""
        try:
            cursor = self.mb_conn.cursor()
            query = """
            SELECT id, url, domain, name, description, country, language,
                   paywall, paywall_type, last_verified, metadata, created_at, updated_at
            FROM sources WHERE id = %s
            """
            cursor.execute(query, (source_id,))
            row = cursor.fetchone()
            cursor.close()

            if row:
                return Source.from_row(row)
            return None

        except Exception as e:
            logger.error(f"Failed to get source {source_id}: {e}")
            return None

    def semantic_search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Perform semantic search using ChromaDB + MariaDB"""
        try:
            # Embed the query
            query_embedding = self.embedding_model.encode(query).tolist()

            # Search ChromaDB for similar articles
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=['metadatas', 'documents', 'distances']
            )

            # Enrich results with full article data from MariaDB
            enriched_results = []
            for article_id, metadata, distance in zip(
                results['ids'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                # Get full article from MariaDB
                article = self.get_article_by_id(article_id)
                if article:
                    # Get source information
                    source = None
                    if article.source_id:
                        source = self.get_source_by_id(article.source_id)

                    enriched_results.append({
                        'article': article.to_dict(),
                        'source': source.to_dict() if source else None,
                        'similarity_score': 1.0 - distance,  # Convert distance to similarity
                        'metadata': metadata
                    })

            return enriched_results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    def search_articles_by_text(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search articles by text content in MariaDB"""
        try:
            cursor = self.mb_conn.cursor(dictionary=True)
            search_query = """
            SELECT a.*,
                   s.name as source_name,
                   s.domain as source_domain
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            WHERE a.title LIKE %s OR a.content LIKE %s OR a.summary LIKE %s
            ORDER BY a.created_at DESC
            LIMIT %s
            """
            search_term = f"%{query}%"
            cursor.execute(search_query, (search_term, search_term, search_term, limit))
            results = cursor.fetchall()
            cursor.close()

            return results

        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []

    def get_recent_articles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent articles from MariaDB"""
        try:
            cursor = self.mb_conn.cursor(dictionary=True)
            query = """
            SELECT a.*,
                   s.name as source_name,
                   s.domain as source_domain
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            ORDER BY a.created_at DESC
            LIMIT %s
            """
            cursor.execute(query, (limit,))
            results = cursor.fetchall()
            cursor.close()

            return results

        except Exception as e:
            logger.error(f"Failed to get recent articles: {e}")
            return []

    def get_articles_by_source(self, source_id: Union[int, str], limit: int = 10) -> List[Dict[str, Any]]:
        """Get articles by source from MariaDB"""
        try:
            cursor = self.mb_conn.cursor(dictionary=True)
            query = """
            SELECT a.*,
                   s.name as source_name,
                   s.domain as source_domain
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            WHERE a.source_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s
            """
            cursor.execute(query, (source_id, limit))
            results = cursor.fetchall()
            cursor.close()

            return results

        except Exception as e:
            logger.error(f"Failed to get articles by source {source_id}: {e}")
            return []