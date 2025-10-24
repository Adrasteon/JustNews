"""
Vector Engine - Embedding and Similarity Search
==============================================

Responsibilities:
- Embedding model management and caching
- Vector similarity search operations
- GPU acceleration for embeddings
- Model reloading and optimization

Architecture:
- Shared embedding model with memory caching
- GPU resource management
- Batch processing for efficiency
- Fallback mechanisms for reliability
"""

import os
from typing import Any, Dict, List, Optional

from common.observability import get_logger

try:
    import torch
except Exception:
    torch = None

# Import tools
from agents.memory.tools import get_embedding_model, vector_search_articles_local

# Configure centralized logging
logger = get_logger(__name__)


class VectorEngine:
    """Vector engine for embedding operations and similarity search"""

    def __init__(self):
        self.embedding_model = None
        self.model_loaded = False
        self.device = None

    async def initialize(self):
        """Initialize the vector engine"""
        try:
            # Determine device
            if torch is not None:
                self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            else:
                self.device = None

            # Load embedding model
            self.embedding_model = get_embedding_model()
            if self.embedding_model is not None:
                self.model_loaded = True
                logger.info(f"Vector engine initialized with device: {self.device}")
            else:
                logger.warning("Vector engine initialized but no embedding model available")

        except Exception as e:
            logger.error(f"Failed to initialize vector engine: {e}")
            raise

    async def shutdown(self):
        """Shutdown the vector engine"""
        try:
            # Clear model reference to free memory
            if self.embedding_model is not None:
                # Some models have cleanup methods
                if hasattr(self.embedding_model, 'cpu'):
                    try:
                        self.embedding_model.cpu()
                    except Exception:
                        pass

            self.embedding_model = None
            self.model_loaded = False

            # Clear GPU cache if available
            if torch is not None and torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

            logger.info("Vector engine shutdown completed")

        except Exception as e:
            logger.error(f"Error during vector engine shutdown: {e}")

    async def reload_model(self):
        """Reload the embedding model"""
        try:
            logger.info("Reloading embedding model in vector engine")

            # Clear existing model
            old_model = self.embedding_model
            self.embedding_model = None
            self.model_loaded = False

            # Clear GPU memory
            if torch is not None and torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

            # Load new model
            self.embedding_model = get_embedding_model()
            if self.embedding_model is not None:
                self.model_loaded = True
                logger.info("Embedding model reloaded successfully")
            else:
                logger.error("Failed to reload embedding model")
                # Restore old model if available
                if old_model is not None:
                    self.embedding_model = old_model
                    self.model_loaded = True
                    logger.info("Restored previous embedding model")

        except Exception as e:
            logger.error(f"Error reloading embedding model: {e}")
            raise

    def vector_search_articles_local(self, query: str, top_k: int = 5) -> list:
        """Perform local vector search using the vector engine's embedding model"""
        try:
            if not self.model_loaded or self.embedding_model is None:
                logger.warning("Vector engine not ready for search - no embedding model")
                return []

            # Use the local search function with our embedding model
            results = vector_search_articles_local(query, top_k, self.embedding_model)
            return results

        except Exception as e:
            logger.error(f"Error in vector search: {e}")
            return []

    def generate_embedding(self, text: str) -> Optional[list]:
        """Generate embedding for text"""
        try:
            if not self.model_loaded or self.embedding_model is None:
                logger.warning("Vector engine not ready for embedding generation")
                return None

            # Generate embedding
            embedding = self.embedding_model.encode(text)

            # Convert to list for JSON serialization
            if hasattr(embedding, 'tolist'):
                return embedding.tolist()
            else:
                return list(embedding)

        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    def get_model_info(self) -> dict:
        """Get information about the current embedding model"""
        try:
            info = {
                "model_loaded": self.model_loaded,
                "device": str(self.device) if self.device else None,
                "model_name": None,
                "embedding_dim": None,
            }

            if self.embedding_model is not None:
                # Try to get model name
                if hasattr(self.embedding_model, 'get_sentence_embedding_dimension'):
                    info["embedding_dim"] = self.embedding_model.get_sentence_embedding_dimension()
                elif hasattr(self.embedding_model, 'encode'):
                    # Test embedding to get dimension
                    try:
                        test_emb = self.embedding_model.encode(["test"])
                        info["embedding_dim"] = len(test_emb[0]) if len(test_emb) > 0 else None
                    except Exception:
                        pass

                # Try to get model name/path
                if hasattr(self.embedding_model, '_model_config') and 'model_name_or_path' in self.embedding_model._model_config:
                    info["model_name"] = self.embedding_model._model_config['model_name_or_path']
                elif hasattr(self.embedding_model, 'model_name_or_path'):
                    info["model_name"] = self.embedding_model.model_name_or_path

            return info

        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            return {"error": str(e)}

    def get_stats(self) -> dict:
        """Get vector engine statistics"""
        try:
            stats = {
                "engine": "vector",
                "model_loaded": self.model_loaded,
                "device": str(self.device) if self.device else None,
            }

            # Get model info
            model_info = self.get_model_info()
            stats.update({
                "model_name": model_info.get("model_name"),
                "embedding_dim": model_info.get("embedding_dim"),
            })

            # GPU memory info if available
            if torch is not None and torch.cuda.is_available():
                try:
                    stats["gpu_memory_allocated"] = torch.cuda.memory_allocated() / 1024**2  # MB
                    stats["gpu_memory_reserved"] = torch.cuda.memory_reserved() / 1024**2   # MB
                except Exception:
                    pass

            return stats

        except Exception as e:
            logger.error(f"Error getting vector engine stats: {e}")
            return {"engine": "vector", "error": str(e)}