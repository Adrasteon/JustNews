"""
Synthesizer V2 Engine - 5-Model AI Architecture for Comprehensive Content Synthesis
================================================================

Architecture: BERTopic + BART + T5 + DialoGPT (deprecated) + SentenceTransformer
Performance: GPU-accelerated text clustering, summarization, and synthesis
Integration: Complete V2 upgrade with professional model management

Models:
1. BERTopic: Advanced topic modeling and article clustering
2. BART: Neural abstractive summarization 
3. T5: Text-to-text generation and neutralization
4. DialoGPT (deprecated): Conversational text generation and refinement
5. SentenceTransformer: Semantic embeddings for clustering

Status: V2 Production Ready - Phase 1 Implementation
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from common.observability import get_logger

# Core ML Libraries
try:
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BartForConditionalGeneration,
        BartTokenizer,
        T5ForConditionalGeneration,
        T5Tokenizer,
        pipeline,
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logging.warning("transformers not available - falling back to CPU processing")

try:
    # sentence-transformers availability is checked at runtime in embedding helper
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not available")

try:
    from bertopic import BERTopic
    from bertopic.representation import KeyBERTInspired, MaximalMarginalRelevance
    # optional: ClassTfidfTransformer not required at import time
    BERTOPIC_AVAILABLE = True
except ImportError:
    BERTOPIC_AVAILABLE = False
    logging.warning("BERTopic not available")

try:
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("sklearn not available")

try:
    import umap
    UMAP_AVAILABLE = True
except ImportError:
    UMAP_AVAILABLE = False
    logging.warning("umap-learn not available - using PCA fallback")

# Configuration
FEEDBACK_LOG = os.environ.get("SYNTHESIZER_V2_FEEDBACK_LOG", "./feedback_synthesizer_v2.log")
MODEL_CACHE_DIR = os.environ.get("SYNTHESIZER_V2_CACHE", "./models/synthesizer_v2")


logger = get_logger(__name__)

@dataclass
class SynthesizerV2Config:
    """Configuration for Synthesizer V2 Engine"""

    # Model configurations
    bertopic_model: str = "all-MiniLM-L6-v2"
    bart_model: str = "facebook/bart-large-cnn"
    t5_model: str = "t5-small"
    # Replace deprecated DialoGPT (deprecated) references with an env-configurable lightweight conversational model.
    # Default to a small task-specific model to avoid DialoGPT (deprecated) usage.
    dialogpt_model: str = os.environ.get("SYNTH_DIALOGPT_MODEL", "distilgpt2")
    embedding_model: str = "all-MiniLM-L6-v2"

    # Generation parameters
    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    do_sample: bool = True

    # Clustering parameters
    min_cluster_size: int = 2
    min_samples: int = 1
    n_clusters: int = 5

    # Performance parameters
    batch_size: int = 8
    max_length: int = 1024
    device: str = "cuda" if torch.cuda.is_available() else "cpu"

    # Cache settings
    use_cache: bool = True
    cache_dir: str = MODEL_CACHE_DIR

class SynthesizerV2Engine:
    """
    Advanced 5-Model Synthesis Engine for Content Analysis and Generation
    
    Capabilities:
    - Advanced topic modeling with BERTopic
    - Neural abstractive summarization with BART
    - Text-to-text generation with T5
    - Conversational refinement with DialoGPT (deprecated)  
    - Semantic clustering with SentenceTransformer
    """

    def __init__(self, config: SynthesizerV2Config | None = None):
        self.config = config or SynthesizerV2Config()
        self.device = torch.device(self.config.device)

        # Model containers
        self.models = {}
        self.tokenizers = {}
        self.pipelines = {}

        # Initialize models
        self._initialize_models()

        logger.info(f"✅ Synthesizer V2 Engine initialized on {self.device}")

    def _initialize_models(self):
        """Initialize all 5 AI models with proper error handling"""

        try:
            # Model 1: BERTopic for advanced clustering
            self._load_bertopic_model()

            # Model 2: BART for summarization
            self._load_bart_model()

            # Model 3: T5 for text generation
            self._load_t5_model()

            # Model 4: DialoGPT (deprecated) for refinement
            self._load_dialogpt_model()

            # Model 5: SentenceTransformer for embeddings
            self._load_embedding_model()

        except Exception as e:
            logger.error(f"Error initializing Synthesizer V2 models: {e}")
            raise

    def _load_bertopic_model(self):
        """Load BERTopic model for advanced clustering"""
        try:
            if not BERTOPIC_AVAILABLE:
                logger.warning("BERTopic not available - using KMeans fallback")
                return

            # Advanced BERTopic configuration with representation models
            representation_model = [
                KeyBERTInspired(),
                MaximalMarginalRelevance(diversity=0.2)
            ]

            # Use UMAP for dimensionality reduction with safer parameters
            if UMAP_AVAILABLE:
                umap_model = umap.UMAP(
                    n_neighbors=3,  # Reduced for small datasets
                    n_components=2,  # Reduced dimensionality
                    min_dist=0.0,
                    metric='cosine',
                    random_state=42
                )
            else:
                umap_model = None
                logger.warning("Using PCA fallback for dimensionality reduction")

            self.models['bertopic'] = BERTopic(
                embedding_model=self.config.bertopic_model,
                umap_model=umap_model,
                representation_model=representation_model,  # type: ignore
                min_topic_size=2,  # Minimum required by HDBSCAN
                calculate_probabilities=False,  # Disable for small datasets
                verbose=False
            )

            logger.info("✅ BERTopic model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading BERTopic model: {e}")
            self.models['bertopic'] = None

    def _load_bart_model(self):
        """Load BART model for neural summarization"""
        try:
            if not TRANSFORMERS_AVAILABLE:
                logger.warning("Transformers not available - skipping BART")
                return

            self.models['bart'] = BartForConditionalGeneration.from_pretrained(
                self.config.bart_model,
                cache_dir=self.config.cache_dir,
                torch_dtype=torch.float16 if self.device.type == 'cuda' else torch.float32
            ).to(self.device)  # type: ignore

            self.tokenizers['bart'] = BartTokenizer.from_pretrained(
                self.config.bart_model,
                cache_dir=self.config.cache_dir
            )

            # Create summarization pipeline
            self.pipelines['bart_summarization'] = pipeline(
                "summarization",
                model=self.models['bart'],
                tokenizer=self.tokenizers['bart'],
                device=0 if self.device.type == 'cuda' else -1,
                batch_size=self.config.batch_size
            )

            logger.info("✅ BART summarization model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading BART model: {e}")
            self.models['bart'] = None

    def _load_t5_model(self):
        """Load T5 model for text-to-text generation"""
        try:
            if not TRANSFORMERS_AVAILABLE:
                logger.warning("Transformers not available - skipping T5")
                return

            self.models['t5'] = T5ForConditionalGeneration.from_pretrained(
                self.config.t5_model,
                cache_dir=self.config.cache_dir,
                torch_dtype=torch.float16 if self.device.type == 'cuda' else torch.float32
            ).to(self.device)  # type: ignore

            self.tokenizers['t5'] = T5Tokenizer.from_pretrained(
                self.config.t5_model,
                cache_dir=self.config.cache_dir
            )

            # Create text2text generation pipeline
            self.pipelines['t5_text2text'] = pipeline(
                "text2text-generation",
                model=self.models['t5'],
                tokenizer=self.tokenizers['t5'],
                device=0 if self.device.type == 'cuda' else -1,
                batch_size=self.config.batch_size
            )

            logger.info("✅ T5 text generation model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading T5 model: {e}")
            self.models['t5'] = None

    def _load_dialogpt_model(self):
        """Load conversational refinement model (DialoGPT (deprecated) deprecated).

        Uses the environment variable SYNTH_DIALOGPT_MODEL to select a model. Default: distilgpt2
        """
        try:
            if not TRANSFORMERS_AVAILABLE:
                logger.warning("Transformers not available - skipping conversational refinement model load")
                return

            self.models['dialogpt'] = AutoModelForCausalLM.from_pretrained(
                self.config.dialogpt_model,
                cache_dir=self.config.cache_dir,
                torch_dtype=torch.float16 if self.device.type == 'cuda' else torch.float32
            ).to(self.device)  # type: ignore

            self.tokenizers['dialogpt'] = AutoTokenizer.from_pretrained(
                self.config.dialogpt_model,
                cache_dir=self.config.cache_dir
            )

            # Add padding token if missing
            if self.tokenizers['dialogpt'].pad_token is None:
                self.tokenizers['dialogpt'].pad_token = self.tokenizers['dialogpt'].eos_token

            # Create text generation pipeline
            self.pipelines['dialogpt_generation'] = pipeline(
                "text-generation",
                model=self.models['dialogpt'],
                tokenizer=self.tokenizers['dialogpt'],
                device=0 if self.device.type == 'cuda' else -1,
                batch_size=self.config.batch_size
            )

            logger.info("✅ Conversational refinement model loaded successfully: %s", self.config.dialogpt_model)

        except Exception as e:
            logger.error(f"Error loading DialoGPT (deprecated) model: {e}")
            self.models['dialogpt'] = None

    def _load_embedding_model(self):
        """Load SentenceTransformer model for semantic embeddings"""
        try:
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.warning("SentenceTransformers not available - using TF-IDF fallback")
                return
            try:
                from agents.common.embedding import get_shared_embedding_model
                agent_cache = os.environ.get('SYNTHESIZER_V2_MODEL_CACHE') or str(Path('./agents/synthesizer/models').resolve())
                # Prefer process-local shared model to avoid repeated loads
                self.models['embeddings'] = get_shared_embedding_model(
                    self.config.embedding_model,
                    cache_folder=agent_cache,
                    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
                )
            except Exception as e:
                logger.debug(f"Embedding helper unavailable or failed: {e}")
                # Leave embeddings unset; upper-level logic will handle fallback behavior
                self.models['embeddings'] = None

            logger.info("✅ SentenceTransformer embedding model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading embedding model: {e}")
            self.models['embeddings'] = None

    def log_feedback(self, event: str, details: dict[str, Any]):
        """Log feedback for model performance tracking"""
        try:
            with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()}\t{event}\t{details}\n")
        except Exception as e:
            logger.error(f"Error logging feedback: {e}")

    def cluster_articles_advanced(self, article_texts: list[str]) -> dict[str, Any]:
        """
        Advanced article clustering using BERTopic or fallback methods
        
        Returns:
            Dict containing clusters, topics, and metadata
        """
        if not article_texts:
            return {"clusters": [], "topics": [], "method": "empty"}

        try:
            # Method 1: BERTopic (preferred)
            if self.models.get('bertopic') is not None:
                topics, probabilities = self.models['bertopic'].fit_transform(article_texts)
                topic_info = self.models['bertopic'].get_topic_info()

                # Organize articles by topic
                clusters = {}
                for idx, topic in enumerate(topics):
                    if topic not in clusters:
                        clusters[topic] = []
                    clusters[topic].append(idx)

                result = {
                    "clusters": list(clusters.values()),
                    "topics": topics.tolist(),
                    "topic_info": topic_info.to_dict() if hasattr(topic_info, 'to_dict') else str(topic_info),
                    "probabilities": probabilities.tolist() if probabilities is not None else None,
                    "method": "bertopic",
                    "n_topics": len(set(topics))
                }

                self.log_feedback("cluster_articles_advanced", {
                    "method": "bertopic",
                    "n_articles": len(article_texts),
                    "n_topics": len(set(topics))
                })

                return result

            # Method 2: Embedding + KMeans fallback
            elif self.models.get('embeddings') is not None and SKLEARN_AVAILABLE:
                embeddings = self.models['embeddings'].encode(article_texts)

                n_clusters = min(self.config.n_clusters, len(article_texts))
                kmeans = KMeans(n_clusters=n_clusters, random_state=42)
                labels = kmeans.fit_predict(embeddings)

                clusters = [[] for _ in range(n_clusters)]
                for idx, label in enumerate(labels):
                    clusters[label].append(idx)

                result = {
                    "clusters": clusters,
                    "topics": labels.tolist(),
                    "method": "embeddings_kmeans",
                    "n_topics": n_clusters
                }

                self.log_feedback("cluster_articles_advanced", {
                    "method": "embeddings_kmeans",
                    "n_articles": len(article_texts),
                    "n_clusters": n_clusters
                })

                return result

            # Method 3: Simple text clustering fallback
            else:
                # Basic clustering using length and keywords
                clusters = self._simple_text_clustering(article_texts)

                result = {
                    "clusters": clusters,
                    "topics": list(range(len(clusters))),
                    "method": "simple_text",
                    "n_topics": len(clusters)
                }

                return result

        except Exception as e:
            logger.error(f"Error in advanced clustering: {e}")
            self.log_feedback("cluster_articles_error", {
                "error": str(e),
                "n_articles": len(article_texts)
            })

            # Return simple fallback
            return {
                "clusters": [list(range(len(article_texts)))],
                "topics": [0] * len(article_texts),
                "method": "fallback_single",
                "error": str(e)
            }

    def _simple_text_clustering(self, texts: list[str]) -> list[list[int]]:
        """Simple text clustering based on length and basic features"""
        if len(texts) <= 1:
            return [list(range(len(texts)))]

        # Cluster by text length
        lengths = [len(text) for text in texts]
        median_length = np.median(lengths)

        short_cluster = []
        long_cluster = []

        for idx, length in enumerate(lengths):
            if length <= median_length:
                short_cluster.append(idx)
            else:
                long_cluster.append(idx)

        return [cluster for cluster in [short_cluster, long_cluster] if cluster]

    def summarize_content_bart(self, text: str, max_length: int = 150) -> str:
        """Generate neural abstractive summary using BART"""
        try:
            if self.pipelines.get('bart_summarization') is None:
                return self._fallback_summarization(text, max_length)

            # Truncate input if too long
            max_input_length = 1024
            if len(text) > max_input_length:
                text = text[:max_input_length]

            result = self.pipelines['bart_summarization'](
                text,
                max_length=max_length,
                min_length=30,
                do_sample=False,
                temperature=0.7
            )

            summary = result[0]['summary_text'] if result else text[:max_length]

            self.log_feedback("summarize_content_bart", {
                "input_length": len(text),
                "output_length": len(summary),
                "model": "bart"
            })

            return summary

        except Exception as e:
            logger.error(f"Error in BART summarization: {e}")
            return self._fallback_summarization(text, max_length)

    def neutralize_text_t5(self, text: str) -> str:
        """Neutralize text bias using T5 text-to-text generation"""
        try:
            if self.pipelines.get('t5_text2text') is None:
                return self._fallback_neutralization(text)

            prompt = f"neutralize bias: {text}"

            result = self.pipelines['t5_text2text'](
                prompt,
                max_length=self.config.max_length,
                temperature=self.config.temperature,
                do_sample=True,
                top_p=self.config.top_p
            )

            neutralized = result[0]['generated_text'] if result else text

            # Clean up T5 artifacts
            if neutralized.startswith("neutralize bias:"):
                neutralized = neutralized.replace("neutralize bias:", "").strip()

            self.log_feedback("neutralize_text_t5", {
                "input_length": len(text),
                "output_length": len(neutralized),
                "model": "t5"
            })

            return neutralized

        except Exception as e:
            logger.error(f"Error in T5 neutralization: {e}")
            return self._fallback_neutralization(text)

    def refine_content_dialogpt(self, text: str, context: str = "news article") -> str:
        """Refine content using DialoGPT (deprecated) conversational capabilities"""
        try:
            if self.pipelines.get('dialogpt_generation') is None:
                return self._fallback_refinement(text)

            prompt = f"Improve this {context} for clarity and readability: {text}"

            result = self.pipelines['dialogpt_generation'](
                prompt,
                max_new_tokens=self.config.max_new_tokens,
                temperature=self.config.temperature,
                do_sample=self.config.do_sample,
                pad_token_id=self.tokenizers['dialogpt'].eos_token_id,
                eos_token_id=self.tokenizers['dialogpt'].eos_token_id
            )

            refined = result[0]['generated_text'] if result else text

            # Extract only the new content
            if refined.startswith(prompt):
                refined = refined[len(prompt):].strip()

            self.log_feedback("refine_content_dialogpt", {
                "input_length": len(text),
                "output_length": len(refined),
                "model": "dialogpt"
            })

            return refined if refined else text

        except Exception as e:
            logger.error(f"Error in DialoGPT (deprecated) refinement: {e}")
            return self._fallback_refinement(text)

    def aggregate_cluster_content(self, article_texts: list[str]) -> dict[str, str]:
        """
        Comprehensive cluster aggregation using all available models
        
        Returns:
            Dict with different aggregation methods
        """
        if not article_texts:
            return {"error": "No articles to aggregate"}

        results = {}
        combined_text = " ".join(article_texts)

        try:
            # Method 1: BART summarization
            if self.models.get('bart') is not None:
                results['bart_summary'] = self.summarize_content_bart(combined_text, max_length=200)

            # Method 2: T5 neutralization
            if self.models.get('t5') is not None:
                results['t5_neutral'] = self.neutralize_text_t5(combined_text[:500])  # Limit input

            # Method 3: DialoGPT (deprecated) refinement
            if self.models.get('dialogpt') is not None:
                results['dialogpt_refined'] = self.refine_content_dialogpt(combined_text[:400])

            # Method 4: Combined best summary
            best_summary = self._select_best_aggregation(results, combined_text)
            results['best_aggregation'] = best_summary

            self.log_feedback("aggregate_cluster_content", {
                "n_articles": len(article_texts),
                "methods_used": list(results.keys()),
                "total_input_length": len(combined_text)
            })

            return results

        except Exception as e:
            logger.error(f"Error in cluster aggregation: {e}")
            return {"error": str(e), "fallback": combined_text[:300]}

    def _select_best_aggregation(self, results: dict[str, str], original: str) -> str:
        """Select the best aggregation result based on quality heuristics"""
        if not results:
            return original[:300]

        # Prefer BART summary if available and reasonable length
        if 'bart_summary' in results and 50 <= len(results['bart_summary']) <= 400:
            return results['bart_summary']

        # Fall back to T5 neutralized version
        if 't5_neutral' in results and len(results['t5_neutral']) > 20:
            return results['t5_neutral']

        # Use DialoGPT (deprecated) refined version
        if 'dialogpt_refined' in results and len(results['dialogpt_refined']) > 20:
            return results['dialogpt_refined']

        # Final fallback to truncated original
        return original[:300]

    def _fallback_summarization(self, text: str, max_length: int) -> str:
        """Simple extractive summarization fallback"""
        sentences = text.split('. ')
        if len(sentences) <= 2:
            return text[:max_length]

        # Take first and last sentences
        summary = sentences[0] + '. ' + sentences[-1]
        return summary[:max_length]

    def _fallback_neutralization(self, text: str) -> str:
        """Simple bias neutralization fallback"""
        # Remove obvious bias indicators
        bias_words = ['clearly', 'obviously', 'definitely', 'certainly', 'undoubtedly']
        neutralized = text

        for word in bias_words:
            neutralized = neutralized.replace(word, '')

        return neutralized.strip()

    def _fallback_refinement(self, text: str) -> str:
        """Simple text refinement fallback"""
        # Basic cleanup
        refined = text.strip()

        # Remove excessive punctuation
        import re
        refined = re.sub(r'[!]{2,}', '!', refined)
        refined = re.sub(r'[?]{2,}', '?', refined)

        return refined

    def get_model_status(self) -> dict[str, Any]:
        """Get status of all models"""
        status: dict[str, Any] = {
            "bertopic": self.models.get('bertopic') is not None,
            "bart": self.models.get('bart') is not None,
            "t5": self.models.get('t5') is not None,
            "dialogpt": self.models.get('dialogpt') is not None,
            "embeddings": self.models.get('embeddings') is not None,
        }
        total_models = sum(1 for model in self.models.values() if model is not None)
        status["total_models"] = total_models
        return status

    def cleanup(self):
        """Clean up GPU memory and models"""
        try:
            for model_name, model in self.models.items():
                if model is not None and hasattr(model, 'cpu'):
                    model.cpu()
                    del model

            self.models.clear()
            self.tokenizers.clear()
            self.pipelines.clear()

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            logger.info("✅ Synthesizer V2 Engine cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

# Test the engine
def run_synthesizer_v2_engine_test():
    """Test Synthesizer V2 Engine with sample data"""
    try:
        print("🔧 Testing Synthesizer V2 Engine...")

        config = SynthesizerV2Config()
        engine = SynthesizerV2Engine(config)

        # Test data
        sample_articles = [
            "The economy showed strong growth this quarter with GDP increasing by 3.2 percent.",
            "Scientists discovered a new species of marine life in the deep ocean trenches.",
            "The technology company announced record profits and expansion plans for next year.",
            "Environmental activists protested against the new industrial development project."
        ]

        # Test clustering
        print("📊 Testing advanced clustering...")
        clustering_result = engine.cluster_articles_advanced(sample_articles)
        print(f"   Clustering method: {clustering_result['method']}")
        print(f"   Number of topics: {clustering_result.get('n_topics', 'Unknown')}")
        print(f"   Number of clusters: {len(clustering_result.get('clusters', []))}")

        # Test summarization
        print("📝 Testing BART summarization...")
        summary = engine.summarize_content_bart(sample_articles[0])
        print(f"   Summary length: {len(summary)} characters")

        # Test neutralization
        print("⚖️ Testing T5 neutralization...")
        neutralized = engine.neutralize_text_t5(sample_articles[1])
        print(f"   Neutralized length: {len(neutralized)} characters")

        # Test aggregation
        print("🔄 Testing cluster aggregation...")
        aggregation = engine.aggregate_cluster_content(sample_articles[:2])
        print(f"   Aggregation methods: {list(aggregation.keys())}")

        # Model status
        status = engine.get_model_status()
        print(f"📋 Model status: {status['total_models']}/5 models loaded")
        print(f"   BERTopic: {'✅' if status['bertopic'] else '❌'}")
        print(f"   BART: {'✅' if status['bart'] else '❌'}")
        print(f"   T5: {'✅' if status['t5'] else '❌'}")
        print(f"   DialoGPT (deprecated): {'✅' if status['dialogpt'] else '❌'}")
        print(f"   Embeddings: {'✅' if status['embeddings'] else '❌'}")

        engine.cleanup()
        print("✅ Synthesizer V2 Engine test completed successfully")

        return True

    except Exception as e:
        print(f"❌ Synthesizer V2 Engine test failed: {e}")
        return False

if __name__ == "__main__":
    run_synthesizer_v2_engine_test()
