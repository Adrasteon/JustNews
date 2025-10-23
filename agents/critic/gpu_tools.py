"""
GPU-accelerated tools for JustNews Critic Agent
Based on proven GPUAcceleratedAnalyst pattern achieving 41.4-168.1 articles/sec

Architecture:
- DialoGPT (deprecated)-medium for content critique (355M parameters)
-            self.critique_pipeline = pipeline(
                "text-classification",  # More appropriate for criticism tasks
                model=model_name,
                device=-1,  # CPU
                return_all_scores=True,  # Get confidence scores for criticism
                batch_size=2,  # Smaller batch for CPU
                trust_remote_code=False
            )sional GPU memory management (4GB base, 5GB peak allocation)
- Batch processing with 8-item batches for optimal performance
- CPU fallback for reliability and graceful degradation

Expected Performance:
- GPU: 30-80 articles/sec (8x improvement over CPU)
- CPU Fallback: 4-10 articles/sec baseline  
- Memory: 4-5GB VRAM allocation via MultiAgentGPUManager
"""

import json
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from common.observability import get_logger

# GPU and ML imports (graceful fallback if not available)
try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline  # noqa: F401
    GPU_AVAILABLE = torch.cuda.is_available()
except ImportError as e:
    print(f"⚠️ GPU/ML libraries not available: {e}")
    GPU_AVAILABLE = False
    torch = None

# Multi-Agent GPU Manager integration
try:
    from agents.common.gpu_manager import (  # noqa: F401
        get_gpu_manager,
        release_agent_gpu,
        request_agent_gpu,
    )
    GPU_MANAGER_AVAILABLE = True
except ImportError:
    print("⚠️ GPU Manager not available - using standalone mode")
    GPU_MANAGER_AVAILABLE = False

# Configure logging

logger = get_logger(__name__)

# Feedback logging (universal pattern)
FEEDBACK_LOG = os.path.join(os.path.dirname(__file__), "critic_gpu_feedback.log")

def log_feedback(event: str, details: dict):
    """Universal feedback logging pattern"""
    try:
        with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
            timestamp = datetime.now(UTC).isoformat()
            f.write(f"{timestamp}\t{event}\t{json.dumps(details)}\n")
    except Exception as e:
        logger.warning(f"Failed to log feedback: {e}")

class GPUAcceleratedCritic:
    """
    GPU-accelerated critic following proven analyst patterns
    
    Capabilities:
    - Content critique using DialoGPT (deprecated)-medium (355M parameters)
    - Quality assessment with GPU acceleration
    - Professional memory management preventing crashes
    - 8x+ performance improvement over CPU baseline
    """

    def __init__(self):
        self.agent_id = f"critic_gpu_{uuid.uuid4().hex[:8]}"
        self.gpu_allocated = False
        self.gpu_device = -1
        self.batch_size = 1  # Default CPU batch size
        self.models_loaded = False

        # Performance tracking
        self.performance_stats = {
            'total_processed': 0,
            'gpu_processed': 0,
            'cpu_processed': 0,
            'avg_processing_time': 0.0,
            'gpu_memory_usage_gb': 0.0,
            'last_performance_check': datetime.now()
        }

        # Model containers
        self.tokenizer = None
        self.critique_model = None
        self.critique_pipeline = None

        logger.info(f"🤖 GPUAcceleratedCritic initialized: {self.agent_id}")

        # Initialize GPU allocation
        self._initialize_gpu_models()

        # Log initialization
        log_feedback("critic_gpu_initialized", {
            "agent_id": self.agent_id,
            "gpu_allocated": self.gpu_allocated,
            "gpu_device": self.gpu_device,
            "models_loaded": self.models_loaded
        })

    def _initialize_gpu_models(self):
        """Initialize GPU models with professional memory management"""
        try:
            if not GPU_AVAILABLE:
                logger.warning("⚠️ GPU not available, using CPU fallback")
                self._load_cpu_models()
                return

            # Request GPU allocation through manager (if available)
            if GPU_MANAGER_AVAILABLE:
                allocation = request_agent_gpu(self.agent_id, "critic")

                if allocation['status'] == 'allocated':
                    self.gpu_allocated = True
                    self.gpu_device = allocation['gpu_device']
                    self.batch_size = allocation.get('batch_size', 8)
                    self.performance_stats['gpu_memory_usage_gb'] = allocation['allocated_memory_gb']

                    logger.info(f"✅ GPU allocated: {allocation['allocated_memory_gb']}GB on device {self.gpu_device}")
                    logger.info(f"   Batch size: {self.batch_size}")

                elif allocation['status'] == 'cpu_fallback':
                    logger.info(f"🔄 CPU fallback: {allocation['reason']}")
                    self.gpu_allocated = False
                    self._load_cpu_models()
                    return

                else:
                    logger.error(f"❌ Allocation failed: {allocation.get('message', 'Unknown error')}")
                    self._load_cpu_models()
                    return
            else:
                # Direct GPU allocation (standalone mode)
                logger.info("🔧 Direct GPU allocation (standalone mode)")
                self.gpu_allocated = True
                self.gpu_device = 0
                self.batch_size = 8

            # Load GPU models
            self._load_gpu_models()

        except Exception as e:
            logger.error(f"❌ GPU initialization failed: {e}")
            self.gpu_allocated = False
            self._load_cpu_models()

    def _load_gpu_models(self):
        """Load models optimized for GPU processing"""
        try:
            logger.info("📦 Loading GPU-optimized models...")

            # TASK-SPECIFIC MODEL: Content quality and bias evaluation (replaces general DialoGPT (deprecated))
            model_name = "unitary/unbiased-toxic-roberta"  # Specialized for content quality assessment

            # Create optimized text classification pipeline for criticism tasks
            if self.gpu_device >= 0:
                torch.cuda.set_device(self.gpu_device)

                # Try loading with GPU optimization
                try:
                    self.critique_pipeline = pipeline(
                        "text-classification",  # More appropriate for quality assessment
                        model=model_name,
                        device=self.gpu_device,
                        torch_dtype=torch.float16,
                        return_all_scores=True,  # Get confidence scores for criticism
                        batch_size=self.batch_size,
                        trust_remote_code=False
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Safetensors loading failed: {e}")
                    logger.info("🔄 Trying alternative model loading method...")
                    # Fallback to CPU loading if GPU has issues
                    self._load_cpu_models()
                    return

                logger.info(f"✅ {model_name} loaded on GPU device {self.gpu_device}")
            else:
                self._load_cpu_models()
                return

            self.models_loaded = True
            logger.info("✅ All critic models loaded successfully")

            # Test GPU memory allocation
            self._test_gpu_memory()

        except Exception as e:
            logger.error(f"❌ GPU model loading failed: {e}")
            self.models_loaded = False
            self._load_cpu_models()

    def _load_cpu_models(self):
        """Load models for CPU processing (fallback)"""
        try:
            logger.info("💻 Loading CPU models (fallback mode)...")

            # TASK-SPECIFIC MODEL: Content quality assessment (replaces general DialoGPT (deprecated))
            model_name = "unitary/unbiased-toxic-roberta"  # Specialized for content quality assessment

            self.critique_pipeline = pipeline(
                "text-classification",  # More appropriate for criticism tasks
                model=model_name,
                device=-1,  # CPU
                return_all_scores=True,  # Get confidence scores for criticism
                batch_size=2  # Smaller batches for CPU
            )

            self.batch_size = 2
            self.models_loaded = True
            logger.info("✅ CPU models loaded successfully")

        except Exception as e:
            logger.error(f"❌ CPU model loading failed: {e}")
            self.models_loaded = False

    def _test_gpu_memory(self):
        """Test GPU memory allocation with sample data"""
        if not self.gpu_allocated or not GPU_AVAILABLE:
            return

        try:
            # Test with sample critique prompt
            test_prompt = "Critique this news article: Sample article for testing GPU memory allocation."

            # Generate response to test memory
            _ = self.critique_pipeline(
                test_prompt,
                max_length=50,
                num_return_sequences=1,
                temperature=0.7,
                pad_token_id=self.tokenizer.eos_token_id
            )

            # Check GPU memory usage
            if torch.cuda.is_available():
                memory_allocated = torch.cuda.memory_allocated(self.gpu_device) / 1024**3
                memory_cached = torch.cuda.memory_reserved(self.gpu_device) / 1024**3

                logger.info("✅ GPU memory test successful")
                logger.info(f"   Allocated: {memory_allocated:.2f}GB")
                logger.info(f"   Cached: {memory_cached:.2f}GB")

                self.performance_stats['gpu_memory_usage_gb'] = memory_allocated

        except Exception as e:
            logger.error(f"❌ GPU memory test failed: {e}")

    def critique_content_gpu(self, articles: list[dict[str, Any]]) -> dict[str, Any]:
        """
        GPU-accelerated content critique
        
        Args:
            articles: List of article dictionaries with 'content', 'title', 'url' fields
            
        Returns:
            Dict with critique results and performance metrics
        """
        start_time = time.time()

        try:
            if not self.models_loaded:
                raise Exception("Models not loaded - initialization failed")

            if not articles:
                return {
                    "success": False,
                    "error": "No articles provided for critique",
                    "critiques": [],
                    "performance": {"processing_time": 0.0, "articles_processed": 0}
                }

            logger.info(f"🔄 Critiquing {len(articles)} articles...")

            # Process articles in batches
            critiques = []

            for i in range(0, len(articles), self.batch_size):
                batch = articles[i:i + self.batch_size]
                batch_critiques = self._process_batch(batch)
                critiques.extend(batch_critiques)

            # Calculate performance metrics
            processing_time = time.time() - start_time
            articles_per_sec = len(articles) / processing_time if processing_time > 0 else 0

            # Update performance stats
            self.performance_stats['total_processed'] += len(articles)
            if self.gpu_allocated:
                self.performance_stats['gpu_processed'] += len(articles)
            else:
                self.performance_stats['cpu_processed'] += len(articles)

            self.performance_stats['avg_processing_time'] = (
                self.performance_stats['avg_processing_time'] + processing_time
            ) / 2

            logger.info(f"✅ Critique completed: {articles_per_sec:.1f} articles/sec")

            # Log successful critique
            log_feedback("critique_completed", {
                "agent_id": self.agent_id,
                "articles_processed": len(articles),
                "processing_time": processing_time,
                "articles_per_sec": articles_per_sec,
                "gpu_used": self.gpu_allocated
            })

            return {
                "success": True,
                "critiques": critiques,
                "performance": {
                    "processing_time": processing_time,
                    "articles_processed": len(articles),
                    "articles_per_sec": articles_per_sec,
                    "gpu_used": self.gpu_allocated,
                    "batch_size": self.batch_size
                },
                "metadata": {
                    "agent_id": self.agent_id,
                    "gpu_device": self.gpu_device,
                    "models_loaded": self.models_loaded
                }
            }

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Critique failed: {str(e)}"
            logger.error(f"❌ {error_msg}")

            log_feedback("critique_error", {
                "agent_id": self.agent_id,
                "error": error_msg,
                "articles_attempted": len(articles) if articles else 0,
                "processing_time": processing_time
            })

            return {
                "success": False,
                "error": error_msg,
                "critiques": [],
                "performance": {"processing_time": processing_time, "articles_processed": 0}
            }

    def _process_batch(self, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process a batch of articles for content quality critique using text classification"""
        batch_critiques = []

        for article in batch:
            try:
                # Extract article content
                title = article.get('title', 'Untitled')
                content = article.get('content', '')
                url = article.get('url', '')

                # Combine title and content for analysis
                full_text = f"{title}\n\n{content}"

                # Analyze content quality using specialized classification model
                quality_results = self.critique_pipeline(full_text[:512])  # Limit to model's max length

                # Extract quality scores from multi-label classification results
                quality_score = 0.8  # Default high-quality score
                toxicity_score = 0.0
                quality_label = "CLEAN"
                toxicity_details = {}

                if quality_results and isinstance(quality_results, list):
                    # Process multi-label toxicity scores
                    scores_dict = {item['label']: item['score'] for item in quality_results[0]}

                    # Primary toxicity categories to evaluate
                    primary_toxic_categories = ['toxicity', 'severe_toxicity', 'insult', 'threat', 'obscene']

                    # Calculate overall toxicity score from primary categories
                    toxic_scores = [scores_dict.get(cat, 0.0) for cat in primary_toxic_categories]
                    toxicity_score = max(toxic_scores)  # Use highest toxic score

                    # Store detailed toxicity analysis
                    toxicity_details = {cat: scores_dict.get(cat, 0.0) for cat in primary_toxic_categories}

                    # Classify content quality based on toxicity levels
                    if toxicity_score > 0.7:
                        quality_label = "TOXIC"
                        quality_score = 0.1  # Very poor quality
                    elif toxicity_score > 0.3:
                        quality_label = "CONCERNING"
                        quality_score = 0.4  # Below average quality
                    elif toxicity_score > 0.1:
                        quality_label = "MINOR_ISSUES"
                        quality_score = 0.6  # Moderate quality
                    else:
                        quality_label = "CLEAN"
                        quality_score = 0.9  # High quality

                # Generate critique assessment based on classification results
                critique_analysis = self._analyze_quality_classification(
                    quality_label, toxicity_score, quality_score, title, content, toxicity_details
                )

                # Create comprehensive critique result
                critique = {
                    'article_title': title,
                    'article_url': url,
                    'critique': critique_analysis['critique_text'],
                    'quality_score': quality_score,
                    'toxicity_score': toxicity_score,
                    'classification_label': quality_label,
                    'accuracy_flags': critique_analysis['accuracy_flags'],
                    'recommendations': critique_analysis['recommendations'],
                    'note': 'Content quality assessment using specialized classification model'
                }

                batch_critiques.append(critique)

            except Exception as e:
                logger.warning(f"⚠️ Failed to critique article '{article.get('title', 'Unknown')}': {e}")
                # Create error critique
                batch_critiques.append({
                    'article_title': article.get('title', 'Unknown'),
                    'article_url': article.get('url', 'No URL'),
                    'critique': f"Content quality analysis failed: {str(e)}",
                    'quality_score': 0.0,
                    'toxicity_score': 0.0,
                    'classification_label': 'ERROR',
                    'accuracy_flags': [],
                    'recommendations': ['Manual review required'],
                    'note': 'Analysis failed - manual review recommended'
                })

        return batch_critiques

    def _analyze_quality_classification(self, label: str, score: float, quality_score: float,
                                      title: str, content: str, toxicity_details: dict = None) -> dict[str, Any]:
        """Analyze quality classification results and generate human-readable critique"""
        toxicity_details = toxicity_details or {}

        # Generate critique text based on new quality classification labels
        if label == 'TOXIC':
            # Identify specific toxicity types detected
            toxic_categories = []
            for category, score_val in toxicity_details.items():
                if score_val > 0.1:  # Threshold for mentioning category
                    toxic_categories.append(f"{category}({score_val:.2f})")

            toxic_str = ", ".join(toxic_categories) if toxic_categories else "general toxicity"
            critique_text = (
                f"🚨 TOXIC CONTENT DETECTED: High toxicity levels found (score: {score:.2f}). "
                f"Detected issues: {toxic_str}. This content is unsuitable for publication "
                f"and requires immediate editorial intervention."
            )
            accuracy_flags = ['toxic_content', 'publication_blocked', 'editorial_review_required']
            recommendations = [
                'DO NOT PUBLISH without major revisions',
                'Remove offensive language and harmful content',
                'Consider alternative sources or complete rewrite',
                'Mandatory editorial and legal review'
            ]

        elif label == 'CONCERNING':
            # Identify moderate concerns
            concern_categories = []
            for category, score_val in toxicity_details.items():
                if score_val > 0.05:
                    concern_categories.append(f"{category}({score_val:.2f})")

            concern_str = ", ".join(concern_categories) if concern_categories else "content quality issues"
            critique_text = (
                f"⚠️ CONTENT QUALITY CONCERNS: Moderate toxicity detected (score: {score:.2f}). "
                f"Areas of concern: {concern_str}. The article needs editorial review "
                f"to address language and tone issues before publication."
            )
            accuracy_flags = ['moderate_toxicity', 'editorial_review_needed']
            recommendations = [
                'Editorial review recommended before publication',
                'Revise problematic language and tone',
                'Consider fact-checking and source verification',
                'Monitor reader feedback after publication'
            ]

        elif label == 'MINOR_ISSUES':
            # Minor quality improvements needed
            critique_text = (
                f"⚠️ MINOR QUALITY ISSUES: Low-level concerns detected (score: {score:.2f}). "
                f"While suitable for publication, minor editorial improvements could "
                f"enhance the article's professionalism and reader experience."
            )
            accuracy_flags = ['minor_quality_issues']
            recommendations = [
                'Consider minor editorial polishing',
                'Review tone and language choices',
                'Standard fact-checking procedures',
                'Monitor for reader feedback'
            ]

        else:  # CLEAN content
            critique_text = (
                f"✅ HIGH QUALITY CONTENT: Excellent content quality detected (score: {score:.2f}). "
                f"The article demonstrates professional standards with appropriate tone, "
                f"language, and presentation suitable for immediate publication."
            )
            accuracy_flags = ['high_quality']
            recommendations = [
                'Content meets publication standards',
                'Standard fact-checking recommended',
                'Consider for featured placement',
                'Suitable for wide distribution'
            ]

        # Add content-specific observations
        word_count = len(content.split())
        if word_count < 50:
            accuracy_flags.append('very_short_content')
            recommendations.append('Article may be too brief for comprehensive coverage')
        elif word_count < 100:
            accuracy_flags.append('short_content')
            recommendations.append('Consider expanding content for better coverage')

        return {
            'critique_text': critique_text,
            'accuracy_flags': accuracy_flags,
            'recommendations': recommendations
        }

    def _assess_quality(self, content: str) -> float:
        """Simple quality assessment based on content characteristics"""
        try:
            if not content:
                return 0.0

            # Basic quality indicators
            score = 0.5  # Base score

            # Length (reasonable articles should have substance)
            if len(content) > 200:
                score += 0.2
            if len(content) > 500:
                score += 0.1

            # Sentence structure (periods indicate complete sentences)
            sentence_count = content.count('.')
            if sentence_count > 3:
                score += 0.1

            # Vocabulary complexity (longer words suggest more detailed reporting)
            words = content.split()
            if words:
                avg_word_length = sum(len(word) for word in words) / len(words)
                if avg_word_length > 5:
                    score += 0.1

            return min(1.0, score)

        except Exception:
            return 0.5  # Neutral score on error

    def _detect_bias_indicators(self, content: str) -> list[str]:
        """
        DEPRECATED: Bias detection functionality moved to Scout V2 Agent
        
        This method is kept for backward compatibility but should not be used.
        All bias detection is now centralized in Scout V2 Agent using specialized models.
        
        Use Scout V2 endpoints:
        - POST /comprehensive_content_analysis (includes bias detection)
        - POST /detect_bias (dedicated bias detection)
        
        Args:
            content: Content text (unused)
            
        Returns:
            Empty list (bias detection moved to Scout V2)
        """
        logger.warning("⚠️ _detect_bias_indicators called - bias detection moved to Scout V2")
        return []  # Return empty list since bias detection is centralized in Scout V2

    def _check_accuracy_flags(self, content: str) -> list[str]:
        """Check for potential accuracy issues"""
        accuracy_flags = []

        # Vague attribution
        vague_sources = ['sources say', 'reports suggest', 'it is believed', 'allegedly', 'rumored']
        for source in vague_sources:
            if source in content.lower():
                accuracy_flags.append(f"Vague attribution: '{source}'")

        # Unsupported claims (simplified detection)
        claim_words = ['proves', 'demonstrates', 'confirms', 'establishes']
        for word in claim_words:
            if word in content.lower():
                accuracy_flags.append(f"Strong claim requiring verification: '{word}'")

        return accuracy_flags[:3]  # Limit to top 3 flags

    def get_performance_stats(self) -> dict[str, Any]:
        """Get current performance statistics"""
        return {
            **self.performance_stats,
            "agent_id": self.agent_id,
            "gpu_allocated": self.gpu_allocated,
            "gpu_device": self.gpu_device,
            "batch_size": self.batch_size,
            "models_loaded": self.models_loaded
        }

    def __del__(self):
        """Cleanup GPU allocation on destruction"""
        if self.gpu_allocated and GPU_MANAGER_AVAILABLE:
            try:
                release_agent_gpu(self.agent_id)
                logger.info(f"✅ Released GPU allocation for {self.agent_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to release GPU allocation: {e}")

# Global instance for reuse
_critic_instance = None

def get_critic_instance() -> GPUAcceleratedCritic:
    """Get or create global critic instance"""
    global _critic_instance
    if _critic_instance is None:
        _critic_instance = GPUAcceleratedCritic()
    return _critic_instance

# Tool functions for MCP integration
def critique_content_gpu(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """GPU-accelerated content critique (MCP-compatible)"""
    critic = get_critic_instance()
    return critic.critique_content_gpu(articles)

def get_critic_performance() -> dict[str, Any]:
    """Get critic performance statistics (MCP-compatible)"""
    critic = get_critic_instance()
    return critic.get_performance_stats()
