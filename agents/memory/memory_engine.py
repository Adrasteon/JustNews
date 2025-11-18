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

# Import tools
from agents.memory.tools import get_embedding_model, log_feedback, save_article
from common.json_utils import make_json_safe
from common.observability import get_logger

# Import database utilities
from database.utils.migrated_database_utils import create_database_service

# Configure centralized logging
logger = get_logger(__name__)


class MemoryEngine:
    """Core memory engine for article storage and retrieval operations"""

    def __init__(self):
        self.db_initialized = False
        self.db_service = None
        self.embedding_model = None

    async def initialize(self):
        """Initialize the memory engine"""
        try:
            # Initialize migrated database service
            self.db_service = create_database_service()
            self.db_initialized = True
            logger.info("Migrated database service initialized for memory engine")

            # Pre-warm embedding model
            self.embedding_model = get_embedding_model()
            logger.info("Embedding model pre-warmed in memory engine")

        except Exception as e:
            logger.error(f"Failed to initialize memory engine: {e}")
            raise

    async def shutdown(self):
        """Shutdown the memory engine"""
        try:
            if self.db_initialized and self.db_service:
                self.db_service.close()
                logger.info("Migrated database service closed in memory engine")

            # Clear references
            self.db_service = None
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

    def get_article(self, article_id: int) -> dict | None:
        """Retrieves an article from the database by its ID"""
        try:
            if not self.db_service:
                return None

            cursor = self.db_service.mb_conn.cursor(dictionary=True)
            cursor.execute("SELECT id, content, metadata FROM articles WHERE id = %s", (article_id,))
            article = cursor.fetchone()
            cursor.close()

            if article:
                # Parse metadata JSON if it's a string
                if isinstance(article.get("metadata"), str):
                    try:
                        article["metadata"] = json.loads(article["metadata"])
                    except Exception:
                        pass
                return article
            else:
                return None
        except Exception as e:
            logger.error(f"Error retrieving article {article_id}: {e}")
            return None

    def get_all_article_ids(self) -> dict:
        """Retrieves all article IDs from the database"""
        try:
            if not self.db_service:
                return {"article_ids": []}

            cursor = self.db_service.mb_conn.cursor(dictionary=True)
            cursor.execute("SELECT id FROM articles")
            rows = cursor.fetchall()
            cursor.close()

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
            if not self.db_service:
                return []

            cursor = self.db_service.mb_conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, content, metadata FROM articles ORDER BY id DESC LIMIT %s",
                (limit,)
            )
            rows = cursor.fetchall()
            cursor.close()

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
            if not self.db_service:
                return {"error": "database_not_initialized"}

            # Insert training example
            cursor = self.db_service.mb_conn.cursor()
            cursor.execute(
                "INSERT INTO training_examples (task, input, output, critique) VALUES (%s, %s, %s, %s)",
                (task, json.dumps(input_data), json.dumps(output_data), critique)
            )
            self.db_service.mb_conn.commit()
            cursor.close()

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

            article_payload = make_json_safe(article_payload)
            if not isinstance(article_payload, dict):
                article_payload = {"value": article_payload}

            statements = statements or []
            statements = make_json_safe(statements)
            if not isinstance(statements, list):
                statements = [statements]

            logger.info(f"Ingesting article: {article_payload.get('url')}")

            # Execute statements transactionally
            chosen_source_id = None

            def _clear_pending_results():
                try:
                    tmp_cursor = self.db_service.mb_conn.cursor()
                    while tmp_cursor.nextset():
                        pass
                    tmp_cursor.close()
                except Exception:
                    pass

            try:
                pending_commit = False
                for sql, params in statements:
                    cursor = None
                    try:
                        sql_upper = sql.upper() if isinstance(sql, str) else ""
                        params_tuple = tuple(params) if params is not None else ()

                        if "RETURNING" in sql_upper:
                            cursor = self.db_service.mb_conn.cursor(dictionary=True, buffered=True)
                            cursor.execute(sql, params_tuple)
                            pending_commit = True

                            result = cursor.fetchone()
                            if result and 'id' in result:
                                chosen_source_id = result['id']

                            try:
                                while cursor.nextset():
                                    cursor.fetchall()
                            except Exception:
                                pass
                        else:
                            cursor = self.db_service.mb_conn.cursor(buffered=True)
                            cursor.execute(sql, params_tuple)
                            pending_commit = True

                    except Exception as stmt_e:
                        try:
                            if cursor is not None:
                                while cursor.nextset():
                                    cursor.fetchall()
                        except Exception:
                            pass

                        try:
                            self.db_service.mb_conn.rollback()
                        except Exception:
                            pass

                        pending_commit = False

                        if "unique constraint" in str(stmt_e).lower() or "duplicate key" in str(stmt_e).lower():
                            logger.debug(f"Source already exists, skipping insert: {stmt_e}")
                            if "sources" in (sql or "") and params_tuple:
                                domain = None
                                if len(params_tuple) > 1:
                                    domain = params_tuple[1]
                                if domain:
                                    lookup_cursor = None
                                    try:
                                        lookup_cursor = self.db_service.mb_conn.cursor(dictionary=True, buffered=True)
                                        lookup_cursor.execute("SELECT id FROM sources WHERE domain = %s", (domain,))
                                        existing_source = lookup_cursor.fetchone()
                                        if existing_source:
                                            chosen_source_id = existing_source['id']
                                            logger.debug(f"Using existing source ID: {chosen_source_id}")
                                    except Exception as lookup_error:
                                        logger.debug(f"Failed to fetch existing source ID: {lookup_error}")
                                    finally:
                                        if lookup_cursor:
                                            try:
                                                lookup_cursor.close()
                                            except Exception:
                                                pass
                            continue

                        raise
                    finally:
                        if cursor:
                            try:
                                cursor.close()
                            except Exception:
                                pass

                if pending_commit:
                    try:
                        self.db_service.mb_conn.commit()
                    except Exception as commit_error:
                        logger.error(f"Failed to commit transaction: {commit_error}")
                        _clear_pending_results()
                        return {"status": "error", "error": str(commit_error)}

            except Exception as e:
                logger.error(f"Database transaction failed: {e}")
                _clear_pending_results()
                return {"status": "error", "error": str(e)}

            # Now save the article content
            try:
                content = article_payload.get("content", "")
                metadata = {
                    "url": article_payload.get("url"),
                    "normalized_url": article_payload.get("normalized_url"),
                    "title": article_payload.get("title"),
                    "summary": article_payload.get("summary"),
                    "analyzed": article_payload.get("analyzed", False),
                    "domain": article_payload.get("domain"),
                    "publisher_meta": article_payload.get("publisher_meta", {}),
                    "confidence": article_payload.get("confidence", 0.5),
                    "paywall_flag": article_payload.get("paywall_flag", False),
                    "extraction_metadata": article_payload.get("extraction_metadata", {}),
                    "structured_metadata": article_payload.get("structured_metadata", {}),
                    "timestamp": article_payload.get("timestamp"),
                    "url_hash": article_payload.get("url_hash"),
                    "url_hash_algorithm": article_payload.get("url_hash_algorithm"),
                    "canonical": article_payload.get("canonical"),
                    "language": article_payload.get("language"),
                    "authors": article_payload.get("authors", []),
                    "section": article_payload.get("section"),
                    "tags": article_payload.get("tags", []),
                    "publication_date": article_payload.get("publication_date"),
                    "raw_html_ref": article_payload.get("raw_html_ref"),
                    "needs_review": article_payload.get("needs_review", False),
                    "review_reasons": article_payload.get("review_reasons", []),
                    "source_id": chosen_source_id,
                    "disable_dedupe": article_payload.get("disable_dedupe"),
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
            if not self.db_service:
                return 0

            cursor = self.db_service.mb_conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) as count FROM articles")
            result = cursor.fetchone()
            cursor.close()

            return result.get("count", 0) if result else 0
        except Exception as e:
            logger.error(f"Error getting article count: {e}")
            # Try to clear any unread results
            try:
                cursor = self.db_service.mb_conn.cursor()
                while cursor.nextset():
                    pass
                cursor.close()
            except Exception:
                pass
            return 0

    def get_sources(self, limit: int = 10) -> list:
        """Get list of sources from the database"""
        try:
            if not self.db_service:
                return []

            cursor = self.db_service.mb_conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, url, domain, name, description, country, language FROM sources ORDER BY id LIMIT %s",
                (limit,)
            )
            sources = cursor.fetchall()
            cursor.close()

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
