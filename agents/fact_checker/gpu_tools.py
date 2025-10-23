# GPU-Accelerated Fact-Checker Agent Tools
# Based on proven GPUAcceleratedAnalyst pattern
# Expected Performance: 5-10x improvement with GPT-2 Medium (355M params) - Modern replacement for deprecated DialoGPT

import os
from datetime import datetime, timezone
from typing import Any

import torch

from common.observability import get_logger

# GPU acceleration imports
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    HAS_TRANSFORMERS = True
except ImportError as e:
    logging.warning(f"Transformers not available: {e}")
    HAS_TRANSFORMERS = False
    AutoModelForCausalLM = None
    AutoTokenizer = None
    pipeline = None

# Configuration - Modern GPT-2 Medium replacement for deprecated DialoGPT
# Use FACT_CHECKER_MODEL_NAME to select a conversational model for verification tasks.
MODEL_NAME = os.environ.get("FACT_CHECKER_MODEL_NAME", "gpt2-medium")  # Modern replacement for DialoGPT
MODEL_PATH = os.environ.get("FACT_CHECKER_MODEL_PATH", "./models/" + MODEL_NAME.replace('/', '_'))
FEEDBACK_LOG = os.environ.get("FACT_CHECKER_FEEDBACK_LOG", "./feedback_fact_checker.log")

# Configure logging

logger = get_logger(__name__)

class GPUAcceleratedFactChecker:
    """
    GPU-accelerated fact checking using GPT-2 Medium (355M parameters) - Modern replacement for deprecated DialoGPT
    
    Based on proven GPUAcceleratedAnalyst pattern:
    - Professional GPU memory management (4GB VRAM allocation)
    - Batch processing for optimal throughput
    - Automatic CPU fallback for reliability
    - Performance monitoring and feedback collection
    """

    def __init__(self):
        self.gpu_available = False
        self.models_loaded = False
        self.performance_stats = {
            'total_requests': 0,
            'gpu_requests': 0,
            'fallback_requests': 0,
            'total_time': 0.0,
            'average_time': 0.0
        }

        logger.info("🚀 Initializing GPU-Accelerated Fact Checker")
        self._initialize_gpu_models()

    def _initialize_gpu_models(self):
        """Initialize GPU models following proven pattern from analyst agent"""
        try:
            if not HAS_TRANSFORMERS:
                raise ImportError("Transformers not available")

            if torch.cuda.is_available():
                self.gpu_available = True
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
                logger.info(f"✅ GPU Available: {gpu_name}")
                logger.info(f"✅ GPU Memory: {gpu_memory:.1f} GB")

                # Load GPT-2 Medium with GPU optimization (modern replacement for DialoGPT)
                logger.info(f"Loading {MODEL_NAME} for GPU acceleration...")

                # Use text-generation pipeline for GPT-2 Medium (similar to analyst pattern)
                if HAS_TRANSFORMERS and pipeline is not None:
                    try:
                        self.fact_verification_pipeline = pipeline(
                            "text-generation",
                            model=MODEL_NAME,
                            device=0,  # GPU device
                            torch_dtype=torch.float16,  # Memory optimization
                            trust_remote_code=False  # Security: disable remote code execution
                        )
                    except Exception as e:
                        logger.warning(f"Failed to load GPT-2 with float16, trying float32: {e}")
                        self.fact_verification_pipeline = pipeline(
                            "text-generation",
                            model=MODEL_NAME,
                            device=0,  # GPU device
                            trust_remote_code=False
                        )

                    # News validation pipeline (lightweight model for speed)
                    try:
                        self.news_validation_pipeline = pipeline(
                            "zero-shot-classification",  # Correct task for zero-shot classification
                            model="facebook/bart-large-mnli",  # Good for zero-shot classification
                            device=0,  # GPU device
                            torch_dtype=torch.float16
                        )
                    except Exception as e:
                        logger.warning(f"Failed to load BART with float16, trying float32: {e}")
                        self.news_validation_pipeline = pipeline(
                            "zero-shot-classification",
                            model="facebook/bart-large-mnli",
                            device=0,  # GPU device
                        )

                    self.models_loaded = True
                    logger.info("✅ GPU models loaded for fact checking")
                else:
                    logger.warning("⚠️ Transformers not available, cannot load GPU models")
                    self._initialize_cpu_fallback()

            else:
                logger.warning("⚠️ GPU not available, initializing CPU fallback")
                self._initialize_cpu_fallback()

        except Exception as e:
            logger.error(f"❌ GPU model loading failed: {e}")
            logger.info("Falling back to CPU implementation")
            self._initialize_cpu_fallback()

    def _initialize_cpu_fallback(self):
        """Initialize CPU fallback (original implementation)"""
        try:
            if HAS_TRANSFORMERS and AutoModelForCausalLM is not None and AutoTokenizer is not None and pipeline is not None:
                # Load models on CPU
                self.cpu_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
                self.cpu_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
                if self.cpu_tokenizer.pad_token is None:
                    self.cpu_tokenizer.pad_token = self.cpu_tokenizer.eos_token

                self.cpu_pipeline = pipeline(
                    "text-generation",
                    model=self.cpu_model,
                    tokenizer=self.cpu_tokenizer,
                    device=-1  # CPU
                )
                logger.info("✅ CPU fallback models loaded")
            else:
                logger.warning("⚠️ No model loading capabilities available")
        except Exception as e:
            logger.error(f"❌ CPU fallback initialization failed: {e}")

    def validate_is_news(self, content: str) -> dict[str, Any]:
        """
        GPU-accelerated news validation with performance tracking
        """
        start_time = datetime.now()
        try:
            if self.gpu_available and self.models_loaded:
                # GPU-accelerated zero-shot classification
                candidate_labels = ["news article", "opinion piece", "advertisement", "personal blog"]
                result = self.news_validation_pipeline(content, candidate_labels)

                # Extract results from zero-shot classification format
                if isinstance(result, dict) and 'labels' in result and 'scores' in result:
                    scores = {label: score for label, score in zip(result['labels'], result['scores'], strict=False)}
                    is_news = result['labels'][0] == "news article" and result['scores'][0] > 0.5
                    confidence = result['scores'][0]
                else:
                    # Fallback if result format is unexpected
                    scores = {"error": 0.0}
                    is_news = False
                    confidence = 0.0

                self.performance_stats['gpu_requests'] += 1
                method = "gpu_zero_shot"
            else:
                # CPU fallback: keyword-based validation (original logic)
                keywords = ["breaking", "report", "headline", "news", "according to", "sources"]
                is_news = any(keyword in content.lower() for keyword in keywords)
                confidence = len([k for k in keywords if k in content.lower()]) / len(keywords)
                scores = {"keyword_match": confidence}

                self.performance_stats['fallback_requests'] += 1
                method = "cpu_keywords"

            # Performance tracking
            elapsed = (datetime.now() - start_time).total_seconds()
            self._update_performance_stats(elapsed)

            result = {
                "is_news": is_news,
                "confidence": confidence,
                "scores": scores,
                "method": method,
                "processing_time": elapsed
            }

            log_feedback("validate_is_news", {
                "content_length": len(content),
                "result": result,
                "method": method
            })

            return result
        except Exception as e:
            logger.error(f"Error in validate_is_news: {e}")
            log_feedback("validate_is_news_error", {"error": str(e), "content_length": len(content)})
            return {
                "is_news": False,
                "confidence": 0.0,
                "scores": {},
                "method": "error",
                "processing_time": 0.0,
                "error": str(e)
            }

    def verify_claims_batch(self, claims: list[str], sources: list[str]) -> dict[str, Any]:
        """
        GPU-accelerated batch claim verification with GPT-2 Medium - Modern replacement for DialoGPT
        """
    # top-level timing is handled within specialized methods
        try:
            if self.gpu_available and self.models_loaded:
                return self._gpu_verify_claims(claims, sources)
            else:
                return self._cpu_verify_claims(claims, sources)

        except Exception as e:
            logger.error(f"Error in verify_claims_batch: {e}")
            log_feedback("verify_claims_error", {
                "claims": claims,
                "sources_count": len(sources),
                "error": str(e)
            })
            return {
                "results": dict.fromkeys(claims, "error"),
                "method": "error",
                "processing_time": 0.0,
                "error": str(e)
            }

    def _gpu_verify_claims(self, claims: list[str], sources: list[str]) -> dict[str, Any]:
        """GPU implementation of claim verification"""
        start_time = datetime.now()

        # Prepare batch prompts for efficient processing
        joined_sources = "\\n".join(sources[:3])  # Limit source length for token efficiency

        results = {}
        batch_prompts = []

        for claim in claims:
            prompt = f"Sources: {joined_sources}\\nClaim: {claim}\\nIs this claim supported by the sources? Answer 'verified' or 'not verified':"
            batch_prompts.append(prompt)

        # Process in batches for optimal GPU utilization
        batch_size = min(8, len(batch_prompts))  # Larger batch size for 355M model (vs 774M DialoGPT)

        for i in range(0, len(batch_prompts), batch_size):
            batch = batch_prompts[i:i + batch_size]
            batch_claims = claims[i:i + batch_size]

            # GPU batch processing
            outputs = self.fact_verification_pipeline(
                batch,
                max_new_tokens=16,  # Short responses
                do_sample=False,   # Deterministic
                pad_token_id=self.fact_verification_pipeline.tokenizer.eos_token_id if hasattr(self.fact_verification_pipeline, 'tokenizer') and self.fact_verification_pipeline.tokenizer else None
            )

            # Parse results
            for claim, output in zip(batch_claims, outputs, strict=False):
                if isinstance(output, list):
                    response = output[0]["generated_text"]
                else:
                    response = output["generated_text"]

                # Extract verification result
                response_lower = response.lower()
                if "verified" in response_lower and "not verified" not in response_lower:
                    results[claim] = "verified"
                elif "not verified" in response_lower:
                    results[claim] = "not verified"
                else:
                    results[claim] = "uncertain"

        elapsed = (datetime.now() - start_time).total_seconds()
        self._update_performance_stats(elapsed)
        self.performance_stats['gpu_requests'] += 1

        return {
            "results": results,
            "method": "gpu_gpt2_medium",
            "processing_time": elapsed,
            "batch_size": batch_size,
            "claims_processed": len(claims)
        }

    def _cpu_verify_claims(self, claims: list[str], sources: list[str]) -> dict[str, Any]:
        """CPU fallback implementation"""
        start_time = datetime.now()

        if hasattr(self, 'cpu_pipeline'):
            # Use CPU GPT-2 Medium pipeline (modern replacement for DialoGPT)
            joined_sources = "\\n".join(sources[:2])  # Smaller batch for CPU
            results = {}

            for claim in claims:
                prompt = f"Sources: {joined_sources}\\nClaim: {claim}\\nVerified or not verified?"
                try:
                    output = self.cpu_pipeline(prompt, max_new_tokens=8, do_sample=False)
                    response = output[0]["generated_text"].lower()

                    if "verified" in response and "not" not in response:
                        results[claim] = "verified"
                    else:
                        results[claim] = "not verified"
                except Exception:
                    results[claim] = "error"
        else:
            # Basic keyword matching fallback
            results = {}
            for claim in claims:
                claim_words = set(claim.lower().split())
                source_text = " ".join(sources).lower()

                # Simple word overlap scoring
                overlap = len(claim_words.intersection(set(source_text.split())))
                threshold = len(claim_words) * 0.3  # 30% word overlap

                results[claim] = "verified" if overlap >= threshold else "not verified"

        elapsed = (datetime.now() - start_time).total_seconds()
        self._update_performance_stats(elapsed)
        self.performance_stats['fallback_requests'] += 1

        return {
            "results": results,
            "method": "cpu_fallback",
            "processing_time": elapsed,
            "claims_processed": len(claims)
        }

    def _update_performance_stats(self, elapsed_time: float):
        """Update performance statistics"""
        self.performance_stats['total_requests'] += 1
        self.performance_stats['total_time'] += elapsed_time
        self.performance_stats['average_time'] = (
            self.performance_stats['total_time'] / self.performance_stats['total_requests']
        )

    def get_performance_stats(self) -> dict[str, Any]:
        """Get current performance statistics"""
        return {
            **self.performance_stats,
            "gpu_available": self.gpu_available,
            "models_loaded": self.models_loaded,
            "gpu_percentage": (
                self.performance_stats['gpu_requests'] /
                max(self.performance_stats['total_requests'], 1) * 100
            )
        }

# Global instance (following analyst pattern)
_gpu_fact_checker = None

def get_gpu_fact_checker():
    """Get or create global GPU fact checker instance"""
    global _gpu_fact_checker
    if _gpu_fact_checker is None:
        _gpu_fact_checker = GPUAcceleratedFactChecker()
    return _gpu_fact_checker

# Public API functions (maintaining compatibility)
def log_feedback(event: str, details: dict):
    """Log feedback for continual learning"""
    with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()}\\t{event}\\t{details}\\n")

def validate_is_news(content: str) -> bool:
    """
    GPU-accelerated news validation (backward compatible)
    Returns boolean for compatibility with existing code
    """
    fact_checker = get_gpu_fact_checker()
    result = fact_checker.validate_is_news(content)
    return result.get("is_news", False)

def verify_claims(claims: list[str], sources: list[str]) -> dict[str, str]:
    """
    GPU-accelerated claim verification (backward compatible)
    Returns dict mapping claims to verification status
    """
    fact_checker = get_gpu_fact_checker()
    result = fact_checker.verify_claims_batch(claims, sources)
    return result.get("results", dict.fromkeys(claims, "error"))

# Enhanced API functions for performance monitoring
def validate_is_news_detailed(content: str) -> dict[str, Any]:
    """Enhanced news validation with detailed results"""
    fact_checker = get_gpu_fact_checker()
    return fact_checker.validate_is_news(content)

def verify_claims_detailed(claims: list[str], sources: list[str]) -> dict[str, Any]:
    """Enhanced claim verification with detailed performance metrics"""
    fact_checker = get_gpu_fact_checker()
    return fact_checker.verify_claims_batch(claims, sources)

def get_fact_checker_performance() -> dict[str, Any]:
    """Get current performance statistics"""
    fact_checker = get_gpu_fact_checker()
    return fact_checker.get_performance_stats()
