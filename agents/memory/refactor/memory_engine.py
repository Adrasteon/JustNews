"""
Memory Engine - Core Storage and Retrieval Logic
===============================================

Responsibilities:
- Article storage and retrieval operations
- Database connection management
- Training example logging
- Article ingestion with transactional operations
- Source management
- Statistics and monitoring

Architecture:
- Database connection pooling
- Transactional operations for data integrity
- Comprehensive error handling
- Performance monitoring and metrics
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from common.observability import get_logger

# Import database utilities
from agents.common.database import close_connection_pool, initialize_connection_pool
from agents.common.database import execute_query, execute_query_single
from agents.common.database import get_db_connection as get_pooled_connection

# Import tools
from agents.memory.refactor.tools import get_embedding_model, log_feedback, save_article

# Configure centralized logging
logger = get_logger(__name__)


class MemoryEngine:
    """Core memory engine for article storage and retrieval operations"""

    def __init__(self):
        self.db_initialized = False
        self.embedding_model = None

    async def initialize(self):
        """Initialize the memory engine"""
        try:
            # Initialize database connection pool
            initialize_connection_pool()
            self.db_initialized = True
            logger.info("Database connection pool initialized for memory engine")

            # Pre-warm embedding model
            self.embedding_model = get_embedding_model()
            logger.info("Embedding model pre-warmed in memory engine")

        except Exception as e:
            logger.error(f"Failed to initialize memory engine: {e}")
            raise

    async def shutdown(self):
        """Shutdown the memory engine"""
        try:
            if self.db_initialized:
                close_connection_pool()
                logger.info("Database connection pool closed in memory engine")

            # Clear embedding model reference
            self.embedding_model = None

        except Exception as e:
            logger.error(f"Error during memory engine shutdown: {e}")

    def save_article(self, content: str, metadata: dict) -> dict:
        """Saves an article to the database and generates an embedding"""
        try:
            # Use the shared save_article function from tools
            result = save_article(content, metadata, embedding_model=self.embedding_model)
            return result
        except Exception as e:
            logger.error(f"Error saving article in memory engine: {e}")
            return {"error": str(e)}

    def get_article(self, article_id: int) -> Optional[dict]:
        """Retrieves an article from the database by its ID"""
        try:
            article = execute_query_single(
                "SELECT id, content, metadata FROM articles WHERE id = %s",
                (article_id,)
            )
            if article:
                return article
            else:
                return None
        except Exception as e:
            logger.error(f"Error retrieving article {article_id}: {e}")
            return None

    def get_all_article_ids(self) -> dict:
        """Retrieves all article IDs from the database"""
        try:
            rows = execute_query("SELECT id FROM articles")
            if rows:
                article_ids = [row['id'] for row in rows]
                logger.info(f"Found {len(article_ids)} article IDs")
                return {"article_ids": article_ids}
            else:
                logger.info("No article IDs found")
                return {"article_ids": []}
        except Exception as e:
            logger.error(f"Error retrieving all article IDs: {e}")
            return {"error": "database_error"}

    def get_recent_articles(self, limit: int = 10) -> list:
        """Returns the most recent articles"""
        try:
            # Fetch most recent articles by id (no created_at column guaranteed)
            rows = execute_query(
                "SELECT id, content, metadata FROM articles ORDER BY id DESC LIMIT %s",
                (limit,)
            ) or []

            # Ensure JSON-serializable metadata
            for r in rows:
                if isinstance(r.get("metadata"), str):
                    try:
                        r["metadata"] = json.loads(r["metadata"])
                    except Exception:
                        pass

            return rows

        except Exception as e:
            logger.error(f"Error retrieving recent articles: {e}")
            return []

    def log_training_example(self, task: str, input_data: dict, output_data: dict, critique: str) -> dict:
        """Logs a training example to the database"""
        try:
            # Insert training example
            execute_query(
                "INSERT INTO training_examples (task, input, output, critique) VALUES (%s, %s, %s, %s)",
                (task, json.dumps(input_data), json.dumps(output_data), critique),
                fetch=False
            )

            log_feedback("log_training_example", {
                "task": task,
                "input_keys": list(input_data.keys()) if input_data else [],
                "output_keys": list(output_data.keys()) if output_data else [],
                "critique_length": len(critique) if critique else 0
            })

            result = {"status": "logged"}

            # Collect prediction for training
            try:
                from training_system import collect_prediction
                collect_prediction(
                    agent_name="memory",
                    task_type="training_example_logging",
                    input_text=f"Task: {task}, Input: {str(input_data)}, Output: {str(output_data)}, Critique: {critique}",
                    prediction=result,
                    confidence=0.9,  # High confidence for successful logging
                    source_url=""
                )
                logger.debug("📊 Training data collected for training example logging")
            except ImportError:
                logger.debug("Training system not available - skipping data collection")
            except Exception as e:
                logger.warning(f"Failed to collect training data: {e}")

            return result

        except Exception as e:
            logger.error(f"Error logging training example: {e}")
            return {"error": str(e)}

    def ingest_article(self, article_payload: dict, statements: list) -> dict:
        """Handles article ingestion with transactional operations"""
        try:
            if not article_payload:
                raise ValueError("Missing article_payload")

            logger.info(f"Ingesting article: {article_payload.get('url')}")

            # Execute statements transactionally
            chosen_source_id = None
            try:
                for sql, params in statements:
                    try:
                        # Execute each statement - the crawler builds the right SQL
                        if "RETURNING id" in sql.upper():
                            # For statements that return IDs (like source upsert)
                            result = execute_query_single(sql, tuple(params))
                            if result and 'id' in result:
                                chosen_source_id = result['id']
                        else:
                            # For regular inserts
                            execute_query(sql, tuple(params), fetch=False)
                    except Exception as stmt_e:
                        # Handle duplicate key errors for sources gracefully
                        if "unique constraint" in str(stmt_e).lower() or "duplicate key" in str(stmt_e).lower():
                            logger.debug(f"Source already exists, skipping insert: {stmt_e}")
                            # Try to get the existing source ID
                            if "sources" in sql and "domain" in str(params):
                                domain = params[1] if len(params) > 1 else None
                                if domain:
                                    existing_source = execute_query_single("SELECT id FROM sources WHERE domain = %s", (domain,))
                                    if existing_source:
                                        chosen_source_id = existing_source['id']
                                        logger.debug(f"Using existing source ID: {chosen_source_id}")
                        else:
                            # Re-raise non-duplicate errors
                            raise stmt_e

            except Exception as e:
                logger.error(f"Database transaction failed: {e}")
                return {"status": "error", "error": str(e)}

            # Now save the article content
            try:
                content = article_payload.get("content", "")
                metadata = {
                    "url": article_payload.get("url"),
                    "title": article_payload.get("title"),
                    "domain": article_payload.get("domain"),
                    "publisher_meta": article_payload.get("publisher_meta", {}),
                    "confidence": article_payload.get("confidence", 0.5),
                    "paywall_flag": article_payload.get("paywall_flag", False),
                    "extraction_metadata": article_payload.get("extraction_metadata", {}),
                    "timestamp": article_payload.get("timestamp"),
                    "url_hash": article_payload.get("url_hash"),
                    "canonical": article_payload.get("canonical"),
                }

                if content:  # Only save if there's actual content
                    save_result = save_article(content, metadata, embedding_model=self.embedding_model)
                    if save_result.get("status") == "duplicate":
                        logger.info(f"Article already exists, skipping: {article_payload.get('url')}")
                        resp = {
                            "status": "ok",
                            "url": article_payload.get('url'),
                            "duplicate": True,
                            "existing_id": save_result.get("article_id")
                        }
                    else:
                        logger.info(f"Article saved with ID: {save_result.get('article_id')}")
                        resp = {"status": "ok", "url": article_payload.get('url')}
                else:
                    logger.warning(f"No content to save for article: {article_payload.get('url')}")
                    resp = {"status": "ok", "url": article_payload.get('url'), "no_content": True}

            except Exception as e:
                logger.warning(f"Failed to save article content: {e}")
                # Don't fail the whole ingestion if content saving fails
                resp = {
                    "status": "ok",
                    "url": article_payload.get('url'),
                    "content_save_error": str(e)
                }

            return resp

        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            return {"status": "error", "error": str(e)}

    def get_article_count(self) -> int:
        """Get total count of articles in database"""
        try:
            result = execute_query_single("SELECT COUNT(*) as count FROM articles")
            return result.get("count", 0) if result else 0
        except Exception as e:
            logger.error(f"Error getting article count: {e}")
            return 0

    def get_sources(self, limit: int = 10) -> list:
        """Get list of sources from the database"""
        try:
            sources = execute_query(
                "SELECT id, url, domain, name, description, country, language FROM sources ORDER BY id LIMIT %s",
                (limit,)
            )
            return sources or []
        except Exception as e:
            logger.error(f"Error getting sources: {e}")
            return []

    def get_stats(self) -> dict:
        """Get memory engine statistics"""
        try:
            stats = {
                "engine": "memory",
                "db_initialized": self.db_initialized,
                "embedding_model_loaded": self.embedding_model is not None,
            }

            # Get article count
            try:
                article_count = self.get_article_count()
                stats["article_count"] = article_count
            except Exception:
                stats["article_count"] = "error"

            # Get source count
            try:
                source_count = len(self.get_sources(1000))  # Get more to count total
                stats["source_count"] = source_count
            except Exception:
                stats["source_count"] = "error"

            return stats

        except Exception as e:
            logger.error(f"Error getting memory engine stats: {e}")
            return {"engine": "memory", "error": str(e)}