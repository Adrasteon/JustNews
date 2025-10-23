# Optimized Synthesizer Configuration
# Phase 1 Memory Optimization: Context reduction + Lightweight embeddings

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common.observability import get_logger

# Configure centralized logging
logger = get_logger(__name__)

# Import Synthesizer V2 Engine
try:
    from agents.synthesizer.synthesizer_v2_engine import SynthesizerV2Engine
    SYNTHESIZER_V2_AVAILABLE = True
except ImportError as e:
    SYNTHESIZER_V2_AVAILABLE = False
    logger.error(f"❌ Synthesizer V2 Engine not available: {e}")

# Import Synthesizer V3 Production Engine
try:
    from agents.synthesizer.synthesizer_v3_production_engine import (
        SynthesizerV3ProductionEngine,
    )
    SYNTHESIZER_V3_AVAILABLE = True
except ImportError as e:
    SYNTHESIZER_V3_AVAILABLE = False
    logger.error(f"❌ Synthesizer V3 Production Engine not available: {e}")

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
except ImportError:
    AutoModelForCausalLM = None
    AutoTokenizer = None
    pipeline = None
try:
    # Use shared embedding helper to avoid repeated loads across agents
    SentenceTransformer = None
except Exception:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        SentenceTransformer = None
try:
    import numpy as np
except ImportError:
    np = None
try:
    from sklearn.cluster import KMeans
except ImportError:
    KMeans = None
try:
    from bertopic import BERTopic
except ImportError:
    BERTopic = None
try:
    import hdbscan
except ImportError:
    hdbscan = None

# Import GPU-accelerated functions
try:
    from agents.synthesizer.gpu_tools import (
        get_synthesizer_performance as _gpu_performance,
    )
    from agents.synthesizer.gpu_tools import (
        synthesize_news_articles_gpu as _gpu_synthesize,
    )
    GPU_TOOLS_AVAILABLE = True
except ImportError as e:
    GPU_TOOLS_AVAILABLE = False
    logger.error(f"❌ GPU tools not available: {e}")
    _gpu_synthesize = None
    _gpu_performance = None

# ==================== GPU-ACCELERATED FUNCTIONS ====================

def synthesize_news_articles_gpu(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """
    GPU-accelerated news article synthesis with fallback to CPU
    
    Args:
        articles: List of article dictionaries to synthesize
    
    Returns:
        Dict with synthesis results
    """
    if not GPU_TOOLS_AVAILABLE or _gpu_synthesize is None:
        logger.warning("⚠️ GPU tools not available, falling back to CPU synthesis")
        # Fallback to V3 synthesis if available
        if SYNTHESIZER_V3_AVAILABLE:
            article_texts = [article.get('content', '') for article in articles if isinstance(article, dict)]
            return synthesize_content_v3(article_texts)
        else:
            return {"error": "GPU tools not available", "method": "gpu_fallback_failed"}

    try:
        return _gpu_synthesize(articles)
    except Exception as e:
        logger.error(f"❌ GPU synthesis failed: {e}")
        # Fallback to CPU synthesis
        if SYNTHESIZER_V3_AVAILABLE:
            article_texts = [article.get('content', '') for article in articles if isinstance(article, dict)]
            return synthesize_content_v3(article_texts)
        else:
            return {"error": str(e), "method": "gpu_failed_no_fallback"}

def get_synthesizer_performance() -> dict[str, Any]:
    """
    Get synthesizer performance statistics with fallback
    
    Returns:
        Dict with performance statistics
    """
    if not GPU_TOOLS_AVAILABLE or _gpu_performance is None:
        logger.warning("⚠️ GPU tools not available for performance stats")
        return {
            "total_syntheses": 0,
            "average_processing_time": 0.0,
            "gpu_utilization": 0.0,
            "memory_usage": 0.0,
            "method": "cpu_only",
            "engines": get_synthesizer_status()
        }

    try:
        result = _gpu_performance()
        # Ensure expected keys are present
        if "total_syntheses" not in result:
            result["total_syntheses"] = 0
        if "average_processing_time" not in result:
            result["average_processing_time"] = 0.0
        if "gpu_utilization" not in result:
            result["gpu_utilization"] = 0.0
        if "memory_usage" not in result:
            result["memory_usage"] = 0.0
        return result
    except Exception as e:
        logger.error(f"❌ GPU performance stats failed: {e}")
        return {
            "total_syntheses": 0,
            "average_processing_time": 0.0,
            "gpu_utilization": 0.0,
            "memory_usage": 0.0,
            "error": str(e),
            "method": "gpu_failed",
            "engines": get_synthesizer_status()
        }

# ==================== END GPU-ACCELERATED FUNCTIONS ====================

# PHASE 1 OPTIMIZATIONS APPLIED
MODEL_NAME = "distilgpt2"
MODEL_PATH = os.environ.get("MODEL_PATH", "./models/distilgpt2")
SYNTHESIZER_MODEL_CACHE = os.environ.get("SYNTHESIZER_MODEL_CACHE")
EMBEDDING_MODEL = os.environ.get("SENTENCE_TRANSFORMER_MODEL", "all-MiniLM-L6-v2")  # Lightweight embeddings
OPTIMIZED_MAX_LENGTH = 1024  # Reduced from 2048 (clustering tasks don't need full context)
OPTIMIZED_BATCH_SIZE = 4     # Memory-efficient for embeddings processing

FEEDBACK_LOG = os.environ.get("SYNTHESIZER_FEEDBACK_LOG", "./feedback_synthesizer.log")

# Configure centralized logging
logger = get_logger(__name__)

# Online Training Integration
# Import training symbols but defer initialization until runtime to avoid
# network/DB activity during import-time (pytest collection).
try:
    from training_system import (
        add_training_feedback,
        add_user_correction,
        initialize_online_training,
    )
    initialize_online_training = initialize_online_training
    add_training_feedback = add_training_feedback
    add_user_correction = add_user_correction
    ONLINE_TRAINING_AVAILABLE = False
except ImportError:
    initialize_online_training = None
    add_training_feedback = None
    add_user_correction = None
    ONLINE_TRAINING_AVAILABLE = False
    logger.warning("⚠️ Online Training not available for Synthesizer")

# runtime flag to avoid repeated initialization
_online_training_initialized = False

def _ensure_online_training_initialized(update_threshold: int = 40) -> None:
    """Lazily initialize the online training system.

    Call this from FastAPI lifespan or on first use to avoid heavy work at import time.
    """
    global _online_training_initialized, ONLINE_TRAINING_AVAILABLE
    if _online_training_initialized:
        return
    if initialize_online_training is None:
        ONLINE_TRAINING_AVAILABLE = False
        _online_training_initialized = True
        return
    try:
        initialize_online_training(update_threshold=update_threshold)
        ONLINE_TRAINING_AVAILABLE = True
        logger.info("🎓 Online Training lazily initialized for Synthesizer V2")
    except Exception as e:
        ONLINE_TRAINING_AVAILABLE = False
        logger.warning(f"⚠️ Online Training failed to initialize at runtime: {e}")
    finally:
        _online_training_initialized = True

# Initialize Synthesizer Engines globally (deferred)
synthesizer_v2_engine = None
synthesizer_v3_engine = None
_synthesizer_engines_initialized = False

def ensure_synthesizer_engines_initialized():
    """Lazily initialize available synthesizer engines at runtime.

    This avoids heavy model downloads during import and allows test
    collection to remain fast and hermetic.
    """
    global _synthesizer_engines_initialized, synthesizer_v2_engine, synthesizer_v3_engine
    if _synthesizer_engines_initialized:
        return
    _synthesizer_engines_initialized = True

    if SYNTHESIZER_V2_AVAILABLE and synthesizer_v2_engine is None:
        try:
            synthesizer_v2_engine = SynthesizerV2Engine()
            logger.info("🚀 Synthesizer V2 Engine lazily initialized")
        except Exception as e:
            logger.error(f"❌ Failed to lazily initialize Synthesizer V2 Engine: {e}")
            synthesizer_v2_engine = None

    if SYNTHESIZER_V3_AVAILABLE and synthesizer_v3_engine is None:
        try:
            synthesizer_v3_engine = SynthesizerV3ProductionEngine()
            logger.info("🚀 Synthesizer V3 Production Engine lazily initialized")
        except Exception as e:
            logger.error(f"❌ Failed to lazily initialize Synthesizer V3 Production Engine: {e}")
            synthesizer_v3_engine = None

def get_synthesizer_v2_engine():
    """Get V2 engine instance"""
    return synthesizer_v2_engine

def get_synthesizer_v3_engine():
    """Get V3 production engine instance"""
    return synthesizer_v3_engine

def get_dialog_model():
    """Load optimized DialoGPT (deprecated)-medium model with memory-efficient configuration."""
    if AutoModelForCausalLM is None or AutoTokenizer is None:
        raise ImportError("transformers library is not installed.")
    # Resolution order:
    # 1. SYNTHESIZER_MODEL_CACHE env var (per-agent explicit cache)
    # 2. MODEL_STORE_ROOT ModelStore current symlink for 'synthesizer'
    # 3. MODEL_PATH (default local path)

    candidate_path = None
    # 1) explicit per-agent cache
    if SYNTHESIZER_MODEL_CACHE:
        candidate_path = SYNTHESIZER_MODEL_CACHE

    # 2) central ModelStore current for synthesizer
    if candidate_path is None:
        model_store_root = os.environ.get('MODEL_STORE_ROOT')
        if model_store_root:
            try:
                from agents.common.model_store import ModelStore
                ms = ModelStore(Path(model_store_root))
                cur = ms.get_current('synthesizer')
                if cur and cur.exists():
                    candidate_path = str(cur)
            except Exception as e:
                logger.warning(f"ModelStore access failed for synthesizer: {e}")

    # 3) fall back to configured MODEL_PATH
    if candidate_path is None:
        candidate_path = MODEL_PATH

    # Ensure directory exists for downloads
    try:
        os.makedirs(candidate_path, exist_ok=True)
    except Exception:
        # If we cannot create the candidate path, fall back to MODEL_PATH
        candidate_path = MODEL_PATH

    # If candidate path is empty, download into it; otherwise load from local cache
    if not os.path.exists(candidate_path) or not os.listdir(candidate_path):
        logger.info(f"Downloading {MODEL_NAME} to {candidate_path}...")
        model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, cache_dir=candidate_path)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=candidate_path)
    else:
        logger.info(f"Loading {MODEL_NAME} from local cache {candidate_path}...")
        model = AutoModelForCausalLM.from_pretrained(candidate_path)
        tokenizer = AutoTokenizer.from_pretrained(candidate_path)
    return model, tokenizer

def get_embedding_model():
    """Return a shared embedding model for the synthesizer.

    This uses the process-local shared instance when available to avoid
    repeated downloads and high memory usage.
    """
    try:
        # Prefer the shared helper when available
        from agents.common.embedding import get_shared_embedding_model
        agent_cache = os.environ.get('SYNTHESIZER_MODEL_CACHE') or str(Path('./agents/synthesizer/models').resolve())

        # If a central ModelStore is configured, prefer loading the synthesizer's
        # current model from the ModelStore (explicit check). This makes the
        # Synthesizer behavior explicit rather than relying on stack inspection.
        model_store_root = os.environ.get('MODEL_STORE_ROOT')
        if model_store_root:
            try:
                from agents.common.model_store import ModelStore
                ms = ModelStore(Path(model_store_root))
                cur = ms.get_current('synthesizer')
                if cur and cur.exists():
                    # Pass the local path to the shared helper; it will construct
                    # a SentenceTransformer from the directory.
                    return get_shared_embedding_model(str(cur), cache_folder=str(cur))
            except Exception:
                # If ModelStore is unavailable or fails, fall back to agent cache
                pass

        return get_shared_embedding_model(EMBEDDING_MODEL, cache_folder=agent_cache)
    except Exception:
        if SentenceTransformer is None:
            raise ImportError("sentence-transformers library is not installed.")

        # Fallback: attempt to ensure a local copy exists then construct from the local path
        agent_cache = os.environ.get('SYNTHESIZER_MODEL_CACHE') or str(Path('./agents/synthesizer/models').resolve())
        try:
            from agents.common.embedding import ensure_agent_model_exists
            _ = ensure_agent_model_exists(EMBEDDING_MODEL, agent_cache)
            from agents.common.embedding import get_shared_embedding_model
            return get_shared_embedding_model(EMBEDDING_MODEL, cache_folder=agent_cache)
        except Exception:
            # Final fallback: use shared helper if possible
            from agents.common.embedding import get_shared_embedding_model
            return get_shared_embedding_model(EMBEDDING_MODEL, cache_folder=agent_cache)

    # Note: compatibility shims for tests are defined at module level below so
    # they can be monkeypatched during pytest collection.
def log_feedback(event: str, details: dict):
    """Log feedback for continual learning and retraining."""
    with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(UTC).isoformat()}\t{event}\t{details}\n")

def cluster_articles(article_texts: list[str], n_clusters: int = 2) -> dict[str, Any]:
    """Cluster articles using optimized embedding configuration."""
    if not article_texts:
        return {"clusters": [], "cluster_labels": [], "n_clusters": 0, "articles_processed": 0}
    
    result = {"clusters": [], "cluster_labels": [], "n_clusters": 0, "articles_processed": 0}  # Initialize result
    
    try:
        model = get_embedding_model()
        embeddings = model.encode(article_texts)
        method = os.environ.get("SYNTHESIZER_CLUSTER_METHOD", "kmeans").lower()
        clusters = []
        cluster_labels = []
        
        try:
            if method == "bertopic":
                if BERTopic is None:
                    raise ImportError("BERTopic is not installed.")
                topic_model = BERTopic(verbose=False)
                topics, _ = topic_model.fit_transform(article_texts)
                n_clusters = max(topics) + 1 if topics else 0
                clusters = [[] for _ in range(n_clusters)]
                cluster_labels = ["topic_" + str(i) for i in range(n_clusters)]
                for idx, topic in enumerate(topics):
                    if topic >= 0:
                        clusters[topic].append(idx)
            elif method == "hdbscan":
                if hdbscan is None:
                    raise ImportError("hdbscan is not installed.")
                clusterer = hdbscan.HDBSCAN(min_cluster_size=2)
                labels = clusterer.fit_predict(embeddings)
                n_clusters = max(labels) + 1 if labels.size > 0 else 0
                clusters = [[] for _ in range(n_clusters)]
                cluster_labels = ["cluster_" + str(i) for i in range(n_clusters)]
                for idx, label in enumerate(labels):
                    if label >= 0:
                        clusters[label].append(idx)
            else:
                if KMeans is None:
                    raise ImportError("sklearn KMeans is not installed.")
                if len(article_texts) < n_clusters:
                    n_clusters = len(article_texts)
                kmeans = KMeans(n_clusters=n_clusters, random_state=42)
                labels = kmeans.fit_predict(embeddings)
                clusters = [[] for _ in range(n_clusters)]
                cluster_labels = ["cluster_" + str(i) for i in range(n_clusters)]
                for idx, label in enumerate(labels):
                    clusters[label].append(idx)
            
            result = {
                "clusters": clusters,
                "cluster_labels": cluster_labels,
                "n_clusters": len(clusters),
                "articles_processed": len(article_texts),
                "method": method
            }
            
            log_feedback("cluster_articles", {"method": method, "n_clusters": len(clusters), "clusters": clusters})
            return result
            
        except Exception as e:
            logger.error(f"Error in cluster_articles: {e}")
            log_feedback("cluster_articles_error", {"error": str(e), "method": method})
            result = {
                "clusters": [[i for i in range(len(article_texts))]],  # Fallback: all in one cluster
                "cluster_labels": ["fallback_cluster"],
                "n_clusters": 1,
                "articles_processed": len(article_texts),
                "method": "fallback",
                "error": str(e)
            }
            return result
            
    finally:
        # Collect prediction for training
        try:
            confidence = min(0.95, max(0.5, result.get("n_clusters", 1) / max(1, len(article_texts) / 2)))  # Higher confidence for more clusters
            from training_system import collect_prediction
            collect_prediction(
                agent_name="synthesizer",
                task_type="article_clustering",
                input_text=str(article_texts),
                prediction=result,
                confidence=confidence,
                source_url=""
            )
            logger.debug(f"📊 Training data collected for article clustering (confidence: {confidence:.3f})")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

def neutralize_text(text: str) -> dict[str, Any]:
    """Use optimized model to neutralize text with reduced memory usage."""
    if not text or not text.strip():
        return {
            "neutralized_text": "",
            "original_text": text,
            "bias_score": 0.0,
            "processing_time": 0.0,
            "method": "empty_input"
        }

    model, tokenizer = get_dialog_model()
    if pipeline is None:
        raise ImportError("transformers pipeline is not available.")

    # Use optimized pipeline configuration
    pipe = pipeline(
        "text2text-generation",
        model=model,
        tokenizer=tokenizer,
        max_length=OPTIMIZED_MAX_LENGTH,
        batch_size=OPTIMIZED_BATCH_SIZE
    )

    prompt = f"Neutralize the following text for bias and strong language: {text}"
    result = pipe(prompt, max_new_tokens=256)[0]["generated_text"]

    # Calculate a simple bias score based on word analysis
    bias_indicators = ["amazing", "fantastic", "terrible", "worst", "best", "incredible", "absolutely"]
    original_bias_score = sum(1 for word in text.lower().split() if word in bias_indicators) / max(len(text.split()), 1)
    neutralized_bias_score = sum(1 for word in result.lower().split() if word in bias_indicators) / max(len(result.split()), 1)

    log_feedback("neutralize_text", {"input": text, "output": result})
    
    result_dict = {
        "neutralized_text": result,
        "original_text": text,
        "bias_score": neutralized_bias_score,
        "original_bias_score": original_bias_score,
        "processing_time": 0.0,  # Would need timing implementation
        "method": "dialogpt_neutralization"
    }
    
    # Collect prediction for training
    try:
        confidence = min(0.95, max(0.5, 1.0 - neutralized_bias_score))  # Higher confidence for better neutralization
        from training_system import collect_prediction
        collect_prediction(
            agent_name="synthesizer",
            task_type="text_neutralization",
            input_text=text,
            prediction=result_dict,
            confidence=confidence,
            source_url=""
        )
        logger.debug(f"📊 Training data collected for text neutralization (confidence: {confidence:.3f})")
    except ImportError:
        logger.debug("Training system not available - skipping data collection")
    except Exception as e:
        logger.warning(f"Failed to collect training data: {e}")
    
    return result_dict

def aggregate_cluster(article_texts: list[str]) -> dict[str, Any]:
    """Use optimized model to summarize article clusters efficiently."""
    if not article_texts:
        return {
            "summary": "",
            "key_points": [],
            "confidence": 0.0,
            "articles_processed": 0,
            "method": "empty_input"
        }

    model, tokenizer = get_dialog_model()
    if pipeline is None:
        raise ImportError("transformers pipeline is not available.")

    # Use optimized pipeline configuration
    pipe = pipeline(
        "text2text-generation",
        model=model,
        tokenizer=tokenizer,
        max_length=OPTIMIZED_MAX_LENGTH,
        batch_size=OPTIMIZED_BATCH_SIZE
    )

    joined = "\n".join(article_texts)
    prompt = f"Summarize the following articles into a neutral, concise summary: {joined}"
    result = pipe(prompt, max_new_tokens=512)[0]["generated_text"]

    # Extract key points (simple sentence splitting)
    key_points = [point.strip() for point in result.split('.') if point.strip()][:5]  # Max 5 key points

    # Calculate confidence based on summary length and coherence
    confidence = min(0.9, len(result.split()) / 100.0)  # Simple heuristic

    log_feedback("aggregate_cluster", {"input": article_texts, "output": result})
    
    result_dict = {
        "summary": result,
        "key_points": key_points,
        "confidence": confidence,
        "articles_processed": len(article_texts),
        "method": "dialogpt_aggregation"
    }
    
    # Collect prediction for training
    try:
        from training_system import collect_prediction
        collect_prediction(
            agent_name="synthesizer",
            task_type="cluster_aggregation",
            input_text=str(article_texts),
            prediction=result_dict,
            confidence=confidence,
            source_url=""
        )
        logger.debug(f"📊 Training data collected for cluster aggregation (confidence: {confidence:.3f})")
    except ImportError:
        logger.debug("Training system not available - skipping data collection")
    except Exception as e:
        logger.warning(f"Failed to collect training data: {e}")
    
    return result_dict

# ==================== SYNTHESIZER V2 TRAINING-INTEGRATED METHODS ====================

def synthesize_content_v2(article_texts: list[str], synthesis_type: str = "aggregate") -> dict[str, Any]:
    """
    V2 Content synthesis with training integration using 5-model architecture
    
    Args:
        article_texts: List of article texts to synthesize
        synthesis_type: Type of synthesis ('aggregate', 'summarize', 'neutralize', 'refine')
    
    Returns:
        Dict with synthesized content and metadata
    """
    if not synthesizer_v2_engine:
        logger.warning("⚠️ Synthesizer V2 Engine not available, falling back to legacy")
        return {"content": aggregate_cluster(article_texts), "method": "legacy", "confidence": 0.5}

    try:
        start_time = datetime.now(UTC)
        result = {"method": "synthesizer_v2", "synthesis_type": synthesis_type, "input_count": len(article_texts)}

        if synthesis_type == "aggregate":
            # Use V2 engine content aggregation
            aggregated = synthesizer_v2_engine.aggregate_cluster_content(article_texts)
            result["content"] = aggregated.get("best_result", "")
            result["all_results"] = aggregated
            result["confidence"] = 0.9

        elif synthesis_type == "summarize":
            # Use BART summarization for each text then aggregate
            summaries = []
            for text in article_texts:
                summary = synthesizer_v2_engine.summarize_content_bart(text)
                summaries.append(summary)
            result["content"] = " ".join(summaries)
            result["individual_summaries"] = summaries
            result["confidence"] = 0.8

        elif synthesis_type == "neutralize":
            # Use T5 neutralization
            neutralized_texts = []
            for text in article_texts:
                neutralized = synthesizer_v2_engine.neutralize_text_t5(text)
                neutralized_texts.append(neutralized)
            result["content"] = " ".join(neutralized_texts)
            result["individual_neutralized"] = neutralized_texts
            result["confidence"] = 0.85

        elif synthesis_type == "refine":
            # Use DialoGPT (deprecated) refinement
            refined_texts = []
            for text in article_texts:
                refined = synthesizer_v2_engine.refine_content_dialogpt(text)
                refined_texts.append(refined)
            result["content"] = " ".join(refined_texts)
            result["individual_refined"] = refined_texts
            result["confidence"] = 0.75

        else:
            # Default to aggregation
            aggregated = synthesizer_v2_engine.aggregate_cluster_content(article_texts)
            result["content"] = aggregated.get("best_result", "")
            result["confidence"] = 0.7

        # Add performance metrics
        end_time = datetime.now(UTC)
        result["processing_time"] = (end_time - start_time).total_seconds()
        result["timestamp"] = end_time.isoformat()

        # Log feedback for training
        log_feedback("synthesize_content_v2", {
            "synthesis_type": synthesis_type,
            "input_count": len(article_texts),
            "output_length": len(result["content"]),
            "confidence": result["confidence"],
            "processing_time": result["processing_time"]
        })

        # Add training feedback if available
        if ONLINE_TRAINING_AVAILABLE:
            try:
                add_training_feedback(
                    agent_name="synthesizer",
                    task_type=f"synthesis_{synthesis_type}",
                    input_text=str(article_texts),
                    predicted_output=result["content"],
                    actual_output=result["content"],  # For unsupervised learning
                    confidence=result["confidence"]
                )
            except Exception as e:
                logger.warning(f"⚠️ Training feedback failed: {e}")

        return result

    except Exception as e:
        logger.error(f"❌ Synthesizer V2 synthesis failed: {e}")
        # Fallback to legacy method
        return {
            "content": aggregate_cluster(article_texts),
            "method": "fallback",
            "error": str(e),
            "confidence": 0.3
        }

def cluster_and_synthesize_v2(article_texts: list[str], n_clusters: int = 2) -> dict[str, Any]:
    """
    V2 Advanced clustering and synthesis with training integration
    
    Args:
        article_texts: List of article texts to cluster and synthesize
        n_clusters: Number of clusters to create
    
    Returns:
        Dict with clustered and synthesized content
    """
    if not synthesizer_v2_engine:
        logger.warning("⚠️ Synthesizer V2 Engine not available")
        return {"error": "V2 engine not available"}

    try:
        start_time = datetime.now(UTC)

        # Advanced clustering with V2 engine
        clustering_result = synthesizer_v2_engine.cluster_articles_advanced(article_texts)
        clusters = clustering_result.get("clusters", [])

        # Synthesize content for each cluster
        synthesized_clusters = []
        for i, cluster_indices in enumerate(clusters):
            if not cluster_indices:
                continue

            cluster_texts = [article_texts[idx] for idx in cluster_indices]
            cluster_synthesis = synthesize_content_v2(cluster_texts, synthesis_type="aggregate")

            synthesized_clusters.append({
                "cluster_id": i,
                "article_indices": cluster_indices,
                "article_count": len(cluster_indices),
                "synthesized_content": cluster_synthesis["content"],
                "confidence": cluster_synthesis["confidence"]
            })

        end_time = datetime.now(UTC)
        result = {
            "method": "synthesizer_v2_clustering",
            "total_articles": len(article_texts),
            "clusters_created": len(synthesized_clusters),
            "synthesized_clusters": synthesized_clusters,
            "clustering_metadata": clustering_result,
            "processing_time": (end_time - start_time).total_seconds(),
            "timestamp": end_time.isoformat()
        }

        # Training feedback
        if ONLINE_TRAINING_AVAILABLE:
            try:
                from numpy import mean
                add_training_feedback(
                    agent_name="synthesizer",
                    task_type="cluster_synthesis",
                    input_text=str(article_texts),
                    predicted_output=str(result),
                    actual_output=str(result),  # For unsupervised learning
                    confidence=mean([c["confidence"] for c in synthesized_clusters]) if synthesized_clusters else 0.5
                )
            except Exception as e:
                logger.warning(f"⚠️ Training feedback failed: {e}")

        return result

    except Exception as e:
        logger.error(f"❌ Cluster and synthesis V2 failed: {e}")
        return {"error": str(e), "method": "failed"}

def add_synthesis_correction(original_input: str, expected_output: str, synthesis_type: str = "aggregate") -> dict[str, Any]:
    """
    Add user correction for synthesis training
    
    Args:
        original_input: Original input text
        expected_output: Expected synthesis output  
        synthesis_type: Type of synthesis task
    
    Returns:
        Dict with correction status
    """
    if not ONLINE_TRAINING_AVAILABLE:
        return {"status": "error", "message": "Online training not available"}

    try:
        add_user_correction(
            agent_name="synthesizer",
            task_type=f"synthesis_{synthesis_type}",
            input_text=original_input,
            incorrect_output="",  # We don't have the incorrect output
            correct_output=expected_output,
            priority=2  # High priority for synthesis corrections
        )

        logger.info(f"✅ Synthesis correction added: {synthesis_type}")
        return {"status": "success", "message": "Correction added successfully"}

    except Exception as e:
        logger.error(f"❌ Failed to add synthesis correction: {e}")
        return {"status": "error", "message": str(e)}

# ==================== END SYNTHESIZER V2 METHODS ====================

# ==================== SYNTHESIZER V3 PRODUCTION METHODS ====================

def synthesize_content_v3(article_texts: list[str], context: str = "news analysis") -> dict[str, Any]:
    """
    V3 Production content synthesis with training integration using 4-model architecture
    
    Features:
    - BERTopic clustering with proper UMAP parameters
    - BART summarization with minimum text validation  
    - FLAN-T5 neutralization and refinement (DialoGPT (deprecated) replacement)
    - SentenceTransformers embeddings
    - Training system integration with feedback collection
    - Comprehensive error handling and fallbacks
    
    Args:
        article_texts: List of article texts to synthesize
        context: Context for synthesis (default: "news analysis")
    
    Returns:
        Dict with synthesis results and metadata
    """
    if not SYNTHESIZER_V3_AVAILABLE:
        logger.warning("V3 engine not available, falling back to V2")
        return synthesize_content_v2(article_texts, context)

    engine = get_synthesizer_v3_engine()
    if engine is None:
        logger.warning("V3 engine not initialized, falling back to V2")
        return synthesize_content_v2(article_texts, context)

    try:
        logger.info(f"🧠 V3 Production synthesis starting: {len(article_texts)} articles")

        # Use V3 cluster and synthesize method
        result = engine.cluster_and_synthesize(article_texts)

        if not result.get('success', False):
            logger.warning("V3 cluster and synthesize failed, using content aggregation")
            # Fallback to direct content aggregation
            aggregated = engine.aggregate_cluster_content(article_texts)
            result = {
                "synthesis": aggregated.get("best_result", ""),
                "clusters": [[i for i in range(len(article_texts))]],
                "n_clusters": 1,
                "articles_processed": len(article_texts),
                "success": True,
                "fallback_used": True,
                "aggregation_details": aggregated
            }

        # Add V3-specific metadata
        result.update({
            "engine": "v3_production",
            "method": "cluster_and_synthesize_v3",
            "context": context,
            "timestamp": datetime.now(UTC).isoformat(),
            "model_info": {
                "bertopic": "clustering",
                "bart": "summarization",
                "flan_t5": "neutralization_refinement",
                "embeddings": "semantic_analysis"
            }
        })

        # Log feedback for training
        log_feedback("synthesize_content_v3", {
            "articles_processed": len(article_texts),
            "clusters_found": result.get('n_clusters', 1),
            "synthesis_length": len(result.get('synthesis', '')),
            "success": result.get('success', False),
            "context": context
        })

        # Add training feedback if available
        if ONLINE_TRAINING_AVAILABLE:
            try:
                add_training_feedback(
                    agent_name="synthesizer",
                    task_type=f"synthesis_v3_{context}",
                    input_text=str(article_texts),  # Convert to string format
                    predicted_output=result.get('synthesis', ''),
                    actual_output=result.get('synthesis', ''),  # No ground truth yet
                    confidence=result.get('confidence', 0.8)
                )
            except Exception as e:
                logger.warning(f"⚠️ V3 Training feedback failed: {e}")

        logger.info(f"✅ V3 Production synthesis completed: {len(result.get('synthesis', ''))} chars")
        return result

    except Exception as e:
        logger.error(f"❌ V3 Production synthesis failed: {e}")
        # Fallback to V2 if available
        if SYNTHESIZER_V2_AVAILABLE:
            logger.info("🔄 Falling back to V2 synthesis")
            return synthesize_content_v2(article_texts, context)
        else:
            return {"error": str(e), "method": "v3_failed_no_fallback", "success": False}


def cluster_and_synthesize_v3(article_texts: list[str], max_clusters: int = 5, context: str = "news analysis") -> dict[str, Any]:
    """
    V3 Production advanced clustering and synthesis with training integration
    
    Features:
    - Advanced BERTopic clustering with proper UMAP configuration
    - Per-cluster BART summarization
    - FLAN-T5 cross-cluster synthesis and refinement
    - Training feedback collection
    - Robust error handling with V2 fallback
    
    Args:
        article_texts: List of article texts to cluster and synthesize
        max_clusters: Maximum number of clusters to create
        context: Context for synthesis
    
    Returns:
        Dict with clustering results and synthesized content
    """
    if not SYNTHESIZER_V3_AVAILABLE:
        logger.warning("V3 engine not available, falling back to V2")
        return cluster_and_synthesize_v2(article_texts, max_clusters, context)

    engine = get_synthesizer_v3_engine()
    if engine is None:
        logger.warning("V3 engine not initialized, falling back to V2")
        return cluster_and_synthesize_v2(article_texts, max_clusters, context)

    try:
        logger.info(f"🎯 V3 Production clustering starting: {len(article_texts)} articles, max {max_clusters} clusters")

        # Step 1: Advanced clustering
        cluster_results = engine.cluster_articles_advanced(article_texts)

        if not cluster_results.get('success', False):
            logger.warning("V3 clustering failed, using fallback approach")
            # Fallback: treat all as one cluster
            result = {
                "clusters": [[i for i in range(len(article_texts))]],
                "n_clusters": 1,
                "cluster_labels": ["general"] * len(article_texts),
                "synthesis": "",
                "articles_processed": len(article_texts),
                "success": False,
                "fallback_used": True
            }
        else:
            result = cluster_results.copy()

        # Step 2: Synthesize content for each cluster
        cluster_syntheses = []
        clusters = result.get('clusters', [[i for i in range(len(article_texts))]])

        for i, cluster_indices in enumerate(clusters):
            if not cluster_indices:
                continue

            cluster_articles = [article_texts[idx] for idx in cluster_indices if idx < len(article_texts)]
            if not cluster_articles:
                continue

            logger.info(f"🔄 Processing cluster {i+1}: {len(cluster_articles)} articles")

            # Use V3 content aggregation for this cluster
            cluster_synthesis = engine.aggregate_cluster_content(cluster_articles)
            cluster_syntheses.append({
                "cluster_id": i,
                "cluster_size": len(cluster_articles),
                "synthesis": cluster_synthesis.get("best_result", ""),
                "synthesis_details": cluster_synthesis
            })

        # Step 3: Final cross-cluster synthesis using FLAN-T5
        if cluster_syntheses:
            all_cluster_syntheses = [cs["synthesis"] for cs in cluster_syntheses if cs["synthesis"]]
            if all_cluster_syntheses:
                try:
                    # Use FLAN-T5 for final refinement
                    final_synthesis = engine.refine_content_flan_t5(
                        " ".join(all_cluster_syntheses),
                        context=f"multi-cluster {context}"
                    )
                    result["synthesis"] = final_synthesis
                except Exception as e:
                    logger.warning(f"FLAN-T5 final synthesis failed: {e}")
                    result["synthesis"] = " ".join(all_cluster_syntheses)
            else:
                result["synthesis"] = ""
        else:
            result["synthesis"] = ""

        # Add V3-specific metadata
        result.update({
            "engine": "v3_production",
            "method": "cluster_and_synthesize_v3",
            "context": context,
            "max_clusters": max_clusters,
            "cluster_syntheses": cluster_syntheses,
            "timestamp": datetime.now(UTC).isoformat(),
            "success": len(result.get("synthesis", "")) > 0
        })

        # Training feedback
        log_feedback("cluster_and_synthesize_v3", {
            "articles_processed": len(article_texts),
            "clusters_found": result.get('n_clusters', 1),
            "synthesis_length": len(result.get('synthesis', '')),
            "max_clusters": max_clusters,
            "success": result.get('success', False),
            "context": context
        })

        if ONLINE_TRAINING_AVAILABLE:
            try:
                add_training_feedback(
                    agent_name="synthesizer",
                    task_type=f"clustering_v3_{context}",
                    input_text=str(article_texts),  # Convert to string format
                    predicted_output=result.get('synthesis', ''),
                    actual_output=result.get('synthesis', ''),  # No ground truth yet
                    confidence=result.get('confidence', 0.8)
                )
            except Exception as e:
                logger.warning(f"⚠️ V3 Clustering training feedback failed: {e}")

        logger.info(f"✅ V3 Production clustering completed: {result.get('n_clusters', 1)} clusters, {len(result.get('synthesis', ''))} chars")
        return result

    except Exception as e:
        logger.error(f"❌ V3 Production clustering failed: {e}")
        # Fallback to V2 if available
        if SYNTHESIZER_V2_AVAILABLE:
            logger.info("🔄 Falling back to V2 clustering")
            return cluster_and_synthesize_v2(article_texts, max_clusters, context)
        else:
            return {"error": str(e), "method": "v3_clustering_failed", "success": False}


def add_synthesis_correction_v3(original_input: str, expected_output: str, synthesis_type: str = "aggregate") -> dict[str, Any]:
    """
    Add user correction for V3 synthesis training
    
    Args:
        original_input: Original input text
        expected_output: Expected synthesis output  
        synthesis_type: Type of synthesis task
    
    Returns:
        Dict with correction status
    """
    if not ONLINE_TRAINING_AVAILABLE:
        return {"status": "error", "message": "Online training not available"}

    try:
        add_user_correction(
            agent_name="synthesizer",
            task_type=f"synthesis_v3_{synthesis_type}",
            input_text=original_input,
            incorrect_output="",  # We don't have the incorrect output
            correct_output=expected_output,
            priority=2  # High priority for synthesis corrections
        )

        logger.info(f"✅ V3 Synthesis correction added: {synthesis_type}")
        return {"status": "success", "message": "V3 correction added successfully", "engine": "v3_production"}

    except Exception as e:
        logger.error(f"❌ Failed to add V3 synthesis correction: {e}")
        return {"status": "error", "message": str(e), "engine": "v3_production"}


def get_synthesizer_status() -> dict[str, Any]:
    """
    Get comprehensive status of both V2 and V3 synthesizer engines
    
    Returns:
        Dict with status of all available engines
    """
    status = {
        "timestamp": datetime.now(UTC).isoformat(),
        "v2_available": SYNTHESIZER_V2_AVAILABLE,
        "v3_available": SYNTHESIZER_V3_AVAILABLE,
        "training_available": ONLINE_TRAINING_AVAILABLE,
        "engines": {}
    }

    # V2 Status
    if SYNTHESIZER_V2_AVAILABLE and synthesizer_v2_engine:
        try:
            v2_status = synthesizer_v2_engine.get_model_status()
            status["engines"]["v2"] = {
                "initialized": True,
                "models": v2_status,
                "architecture": "5_model_legacy"
            }
        except Exception as e:
            status["engines"]["v2"] = {"initialized": False, "error": str(e)}
    elif SYNTHESIZER_V2_AVAILABLE:
        status["engines"]["v2"] = {"initialized": False, "available": True}

    # V3 Status
    if SYNTHESIZER_V3_AVAILABLE and synthesizer_v3_engine:
        try:
            v3_status = synthesizer_v3_engine.get_model_status()
            status["engines"]["v3"] = {
                "initialized": True,
                "models": v3_status,
                "architecture": "4_model_production"
            }
        except Exception as e:
            status["engines"]["v3"] = {"initialized": False, "error": str(e)}
    elif SYNTHESIZER_V3_AVAILABLE:
        status["engines"]["v3"] = {"initialized": False, "available": True}

    # Recommend primary engine
    if SYNTHESIZER_V3_AVAILABLE and synthesizer_v3_engine:
        status["recommended_engine"] = "v3_production"
    elif SYNTHESIZER_V2_AVAILABLE and synthesizer_v2_engine:
        status["recommended_engine"] = "v2_legacy"
    else:
        status["recommended_engine"] = "none_available"

    return status

# ==================== END SYNTHESIZER V3 PRODUCTION METHODS ====================
