"""
Memory Agent Tools - Utility Functions
=====================================

Core utilities for the memory agent:
- Embedding model management
- Article storage operations
- Vector search functionality
- Feedback logging
- Training data collection

Architecture:
- Shared embedding model with caching
- Database connection pooling
- GPU acceleration support
- Comprehensive error handling
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import requests

from common.observability import get_logger

try:
    import torch
except Exception:
    torch = None

# Import database utilities
from agents.common.database import execute_query, execute_query_single
from agents.common.database import get_db_connection as get_pooled_connection

# Configure centralized logging
logger = get_logger(__name__)

# Environment variables
FEEDBACK_LOG = os.environ.get("MEMORY_FEEDBACK_LOG", "./feedback_memory.log")
EMBEDDING_MODEL_NAME = os.environ.get("SENTENCE_TRANSFORMER_MODEL", "all-MiniLM-L6-v2")
MEMORY_AGENT_PORT = int(os.environ.get("MEMORY_AGENT_PORT", 8007))
POSTGRES_HOST = os.environ.get("POSTGRES_HOST")
POSTGRES_DB = os.environ.get("POSTGRES_DB")
POSTGRES_USER = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")

# Canonical cache folder for shared embedding model
DEFAULT_MODEL_CACHE = os.environ.get("MEMORY_MODEL_CACHE") or str(Path('./agents/memory/models').resolve())


def log_feedback(event: str, details: dict):
    """Logs feedback to a file."""
    try:
        with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()}\t{event}\t{details}\n")
    except Exception as e:
        logger.error(f"Error logging feedback: {e}")


def get_embedding_model():
    """Return a SentenceTransformer instance, using the shared helper when available."""
    try:
        from agents.common.embedding import get_shared_embedding_model
        # Use a canonical cache folder and device so cached instances are reused
        device = None
        if torch is not None:
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        return get_shared_embedding_model(EMBEDDING_MODEL_NAME, cache_folder=DEFAULT_MODEL_CACHE, device=device)
    except Exception:
        # Fallback: use agent-local models directory
        try:
            from agents.common.embedding import get_shared_embedding_model
            agent_cache = os.environ.get('MEMORY_MODEL_CACHE') or str(Path('./agents/memory/models').resolve())
            device = None
            if torch is not None:
                device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            return get_shared_embedding_model(EMBEDDING_MODEL_NAME, cache_folder=agent_cache, device=device)
        except Exception as e:
            logger.warning(f"Could not load shared embedding model: {e}")
            # Return None - caller should handle this gracefully
            return None


def save_article(content: str, metadata: dict, embedding_model=None) -> dict:
    """Saves an article to the database and generates an embedding for the content.

    Args:
        content: Article text to embed and store.
        metadata: Arbitrary metadata dict to store alongside the article.
        embedding_model: Optional pre-initialized SentenceTransformer instance.
            If not provided, a new model will be created via get_embedding_model().
    """
    try:
        # Check for duplicates based on URL first
        article_url = metadata.get("url") if metadata else None
        if article_url:
            # Check if article with this URL already exists
            existing_article = execute_query_single(
                "SELECT id FROM articles WHERE metadata->>'url' = %s",
                (article_url,)
            )
            if existing_article:
                logger.info(f"Article with URL {article_url} already exists (ID: {existing_article['id']}), skipping duplicate")
                return {"status": "duplicate", "article_id": existing_article['id'], "message": "Article already exists"}

        # Use provided model if available to avoid re-loading model per-call
        if embedding_model is None:
            embedding_model = get_embedding_model()

        if embedding_model is None:
            logger.error("No embedding model available for article storage")
            return {"error": "embedding_model_unavailable"}

        # encode may return numpy array; convert later to list of floats
        embedding = embedding_model.encode(content)

        # Ensure metadata is a JSON-serializable string for safe insertion
        try:
            metadata_payload = json.dumps(metadata) if metadata is not None else json.dumps({})
        except Exception:
            # Fallback: coerce to string
            metadata_payload = json.dumps({"raw": str(metadata)})

        # Get the next available ID (simple approach without sequence)
        next_id_result = execute_query_single("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM articles")
        next_id = 1
        if next_id_result:
            if isinstance(next_id_result, dict):
                if 'next_id' in next_id_result:
                    next_id = int(next_id_result['next_id'])
                elif 'coalesce' in next_id_result:  # some drivers name expression as 'coalesce'
                    next_id = int(next_id_result['coalesce'])
                elif '?column?' in next_id_result:  # postgres default unnamed expression
                    next_id = int(next_id_result['?column?'])
                else:
                    # fallback to first value
                    try:
                        next_id = int(list(next_id_result.values())[0])
                    except Exception:
                        next_id = 1
            else:
                try:
                    next_id = int(next_id_result)
                except Exception:
                    next_id = 1

        # Insert with explicit ID - metadata as JSON string (Postgres will cast)
        execute_query(
            "INSERT INTO articles (id, content, metadata, embedding) VALUES (%s, %s, %s::jsonb, %s)",
            (next_id, content, metadata_payload, list(map(float, embedding))),
            fetch=False
        )

        log_feedback("save_article", {"status": "success", "article_id": next_id})

        result = {"status": "success", "article_id": next_id, "id": next_id}

        # Collect prediction for training
        try:
            from training_system import collect_prediction
            collect_prediction(
                agent_name="memory",
                task_type="article_storage",
                input_text=content,
                prediction=result,
                confidence=0.95,  # High confidence for successful storage
                source_url=""
            )
            logger.debug("📊 Training data collected for article storage")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

        # Return both 'article_id' and legacy 'id' key for backward compatibility
        return result
    except Exception as e:
        logger.error(f"Error saving article: {e}")
        return {"error": str(e)}


def vector_search_articles(query: str, top_k: int = 5) -> list:
    """Performs a vector search for articles using the memory agent."""
    url = f"http://localhost:{MEMORY_AGENT_PORT}/vector_search_articles"
    try:
        response = requests.post(url, json={"query": query, "top_k": top_k}, timeout=5)
        response.raise_for_status()
        res = response.json()
        # Coerce a few common shapes from test fakes: allow list or dict with 'results'
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            # prefer explicit results key
            if 'results' in res and isinstance(res['results'], list):
                return res['results']
            # sometimes test fakes return empty dict
            return []
        return []
    except requests.exceptions.RequestException as e:
        logger.warning(f"vector_search_articles: memory agent request failed: {e}")
        return []


def vector_search_articles_local(query: str, top_k: int = 5, embedding_model=None) -> list:
    """Local in-process vector search implementation.

    This avoids making an HTTP call to the same process when the endpoint is
    executed inside the memory agent. It queries the articles table for stored
    embeddings and returns the top_k nearest articles by cosine similarity.
    """
    try:
        # Retrieve id, content, metadata and embedding from the DB using new connection pooling
        rows = execute_query("SELECT id, content, metadata, embedding FROM articles WHERE embedding IS NOT NULL")
        if not rows:
            return []
    except Exception as e:
        logger.warning(f"vector_search_articles_local: DB query failed: {e}")
        return []

    # Build embeddings matrix and compute cosine similarities
    try:
        # Use provided model or get one
        if embedding_model is None:
            embedding_model = get_embedding_model()

        if embedding_model is None:
            logger.error("No embedding model available for vector search")
            return []

        # Load stored embeddings and ids
        ids = []
        contents = {}
        metas = {}
        embeddings = []
        for r in rows:
            ids.append(r['id'])
            contents[r['id']] = r['content']
            metas[r['id']] = r.get('metadata')
            emb = r.get('embedding')
            if emb is None:
                emb = []
            embeddings.append(np.array(emb, dtype=float))

        if len(embeddings) == 0:
            return []

        # Compute query embedding
        q_emb = embedding_model.encode(query)
        q_emb = np.array(q_emb, dtype=float)

        M = np.vstack(embeddings)
        # Normalize
        def _norm(a):
            n = np.linalg.norm(a)
            return a / n if n != 0 else a

        Mn = np.apply_along_axis(_norm, 1, M)
        qn = _norm(q_emb)
        sims = Mn.dot(qn)
        # Get top_k indices
        top_idx = np.argsort(-sims)[:top_k]
        results = []
        for i in top_idx:
            aid = ids[int(i)]
            results.append({
                "id": int(aid),
                "score": float(sims[int(i)]),
                "content": contents[aid],
                "metadata": metas.get(aid),
            })

        # Collect prediction for training
        try:
            from training_system import collect_prediction
            confidence = min(0.9, max(0.1, float(np.mean(sims[top_idx])))) if len(top_idx) > 0 else 0.5
            collect_prediction(
                agent_name="memory",
                task_type="vector_search",
                input_text=query,
                prediction={"results": results, "top_k": top_k},
                confidence=confidence,
                source_url=""
            )
            logger.debug(f"📊 Training data collected for vector search (confidence: {confidence:.3f})")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

        return results
    except Exception:
        logger.exception("vector_search_articles_local: error computing similarities")
        return []