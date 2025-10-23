#!/usr/bin/env python3
"""
Native TensorRT Inference Engine for JustNews V4
Ultra-high performance inference using compiled TensorRT engines

Performance Targets:
- 2-4x improvement over baseline (300-600 articles/sec)
- Native CUDA execution with zero Python overhead
- Optimized batch processing up to 100 articles
- FP8/FP16 precision for maximum throughput

Status: PRODUCTION READY - Native TensorRT execution
"""


import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from common.observability import get_logger

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Transformers and model loading imports
from transformers import AutoTokenizer

from agents.common.model_loader import load_transformers_model

logger = get_logger(__name__)

# Environment validation
def _validate_environment():
    """Validate that the required environment is properly set up"""
    try:
        import importlib.util
        if importlib.util.find_spec("numpy") is None:
            raise ImportError("numpy is not available")
    except ImportError:
        raise ImportError(
            "numpy is not available. Please ensure you're using the JustNewsAgent environment:\n"
            "  source activate_environment.sh\n"
            "  python your_script.py"
        )

    try:
        import importlib.util
        if importlib.util.find_spec("torch") is None:
            raise ImportError("PyTorch is not available")
    except ImportError:
        raise ImportError(
            "PyTorch is not available. Please ensure you're using the JustNewsAgent environment:\n"
            "  source activate_environment.sh\n"
            "  python your_script.py"
        )

# Run environment validation
_validate_environment()

# Run environment validation
_validate_environment()

# TensorRT and CUDA imports (optional)
try:
    import pycuda.autoinit  # noqa: F401  (side-effect import for CUDA init)
    import pycuda.driver as cuda  # noqa: F401  (optional GPU dependency)
    import tensorrt as trt
    TENSORRT_AVAILABLE = True
except ImportError:
    TENSORRT_AVAILABLE = False
    # Create dummy objects for type checking
    trt = None
    cuda = None

# Fallback imports
try:
    from .gpu_analyst import GPUAcceleratedAnalyst
except ImportError:
    try:
        from gpu_analyst import GPUAcceleratedAnalyst
    except ImportError:
        GPUAcceleratedAnalyst = None
        logger.warning("⚠️  GPUAcceleratedAnalyst not available - fallback functionality disabled")

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


logger = get_logger(__name__)

# Export availability flag
NATIVE_TENSORRT_AVAILABLE = TENSORRT_AVAILABLE

class NativeTensorRTInferenceEngine:
    """
    Ultra-high performance TensorRT inference engine
    Uses compiled native TensorRT engines for maximum speed
    """

    def __init__(self, engines_dir: str = "agents/analyst/tensorrt_engines", fallback_analyst=None):
        """Initialize native TensorRT inference engine with fallback support"""
        self.engines_dir = Path(engines_dir)
        self.engines = {}
        self.contexts = {}
        self.tokenizers = {}
        self.engine_metadata = {}
        self.cuda_stream = None
        self.cuda_context = None  # Store CUDA context reference
        self.fallback_analyst = fallback_analyst

        # Performance tracking
        self.performance_stats = {
            'native_requests': 0,
            'native_time': 0.0,
            'fallback_requests': 0,
            'fallback_time': 0.0
        }

        self._initialize_cuda()
        self._load_engines()

    def _initialize_cuda(self):
        """Initialize CUDA context and stream with proper context management"""
        if not TENSORRT_AVAILABLE:
            logger.warning("⚠️  TensorRT not available - CUDA initialization skipped")
            self.cuda_stream = None
            self.cuda_context = None
            return

        try:
            # Initialize CUDA explicitly (don't use autoinit)
            cuda.init()

            # Get or create CUDA context properly
            context_created = False
            try:
                # Try to get existing context
                self.cuda_context = cuda.Context.get_current()
                if self.cuda_context is None:
                    # Create new context if none exists
                    device = cuda.Device(0)
                    self.cuda_context = device.make_context()
                    context_created = True
                    logger.info("✅ Created new CUDA context")
                else:
                    logger.info("✅ Using existing CUDA context")
            except cuda.LogicError:
                # No context exists, create one
                device = cuda.Device(0)
                self.cuda_context = device.make_context()
                context_created = True
                logger.info("✅ Created new CUDA context")

            # Store whether we created the context (for cleanup)
            self.context_created = context_created

            # Create stream with proper context
            self.cuda_stream = cuda.Stream()

            # Verify stream is valid
            if self.cuda_stream.handle == 0:
                raise RuntimeError("Invalid CUDA stream handle")

            logger.info("✅ CUDA context initialized for native TensorRT")
            logger.info(f"   Stream handle: {self.cuda_stream.handle}")

        except Exception as e:
            logger.error(f"❌ CUDA initialization failed: {e}")
            raise

    def _load_engines(self):
        """Load native TensorRT engines from disk"""
        try:

            # Load sentiment engine
            sentiment_engine_path = self.engines_dir / "native_sentiment_roberta.engine"
            sentiment_metadata_path = self.engines_dir / "native_sentiment_roberta.json"

            if sentiment_engine_path.exists() and sentiment_metadata_path.exists():
                with open(sentiment_engine_path, 'rb') as f:
                    engine_data = f.read()

                with open(sentiment_metadata_path) as f:
                    metadata = json.load(f)

                runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
                engine = runtime.deserialize_cuda_engine(engine_data)
                context = engine.create_execution_context()

                self.engines['sentiment'] = engine
                self.contexts['sentiment'] = context
                self.engine_metadata['sentiment'] = metadata

                logger.info("✅ sentiment native engine loaded:")
                logger.info(f"   Max Batch Size: {metadata.get('max_batch_size', 'N/A')}")
                logger.info(f"   Precision: {metadata.get('precision', 'N/A').upper()}")

            # Load bias engine
            bias_engine_path = self.engines_dir / "native_bias_bert.engine"
            bias_metadata_path = self.engines_dir / "native_bias_bert.json"

            if bias_engine_path.exists() and bias_metadata_path.exists():
                with open(bias_engine_path, 'rb') as f:
                    engine_data = f.read()

                with open(bias_metadata_path) as f:
                    metadata = json.load(f)

                runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
                engine = runtime.deserialize_cuda_engine(engine_data)
                context = engine.create_execution_context()

                self.engines['bias'] = engine
                self.contexts['bias'] = context
                self.engine_metadata['bias'] = metadata

                logger.info("✅ bias native engine loaded:")
                logger.info(f"   Max Batch Size: {metadata.get('max_batch_size', 'N/A')}")
                logger.info(f"   Precision: {metadata.get('precision', 'N/A').upper()}")

            # Load tokenizers
            self._load_tokenizers()

            if self.engines:
                logger.info(f"✅ Native TensorRT engines loaded: {list(self.engines.keys())}")
            else:
                logger.warning("⚠️  No native TensorRT engines found")

        except Exception as e:
            logger.error(f"❌ Failed to load native engines: {e}")

    def _load_tokenizers(self):
        """Load tokenizers for each task"""
        try:
            # Load sentiment tokenizer (RoBERTa) and bias tokenizer (BERT)
            try:
                if 'sentiment' in self.engines:
                    try:
                        _, tokenizer = load_transformers_model(
                            'cardiffnlp/twitter-roberta-base-sentiment-latest',
                            agent='analyst',
                            cache_dir=None,
                            model_class=None,
                            tokenizer_class=AutoTokenizer,
                        )
                        self.tokenizers['sentiment'] = tokenizer
                    except Exception:
                        self.tokenizers['sentiment'] = AutoTokenizer.from_pretrained(
                            'cardiffnlp/twitter-roberta-base-sentiment-latest'
                        )

                if 'bias' in self.engines:
                    try:
                        _, tokenizer = load_transformers_model(
                            'unitary/toxic-bert',
                            agent='analyst',
                            cache_dir=None,
                            model_class=None,
                            tokenizer_class=AutoTokenizer,
                        )
                        self.tokenizers['bias'] = tokenizer
                    except Exception:
                        self.tokenizers['bias'] = AutoTokenizer.from_pretrained(
                            'unitary/toxic-bert'
                        )
            except Exception:
                # If model_loader import fails entirely, fallback to direct HF loads
                if 'sentiment' in self.engines:
                    self.tokenizers['sentiment'] = AutoTokenizer.from_pretrained(
                        'cardiffnlp/twitter-roberta-base-sentiment-latest'
                    )
                if 'bias' in self.engines:
                    self.tokenizers['bias'] = AutoTokenizer.from_pretrained(
                        'unitary/toxic-bert'
                    )

        except Exception as e:
            logger.error(f"❌ Failed to load tokenizers: {e}")

    def _initialize_engines(self):
        """Initialize all compiled TensorRT engines"""
        try:
            # Create TensorRT runtime
            self.trt_logger = trt.Logger(trt.Logger.WARNING)
            self.runtime = trt.Runtime(self.trt_logger)

            # Load sentiment engine
            self._load_engine('sentiment', 'native_sentiment_roberta.engine',
                            'cardiffnlp/twitter-roberta-base-sentiment-latest')

            # Load bias engine
            self._load_engine('bias', 'native_bias_bert.engine',
                            'unitary/toxic-bert')

            if not self.engines:
                logger.warning("⚠️  No native TensorRT engines found - using fallback")
                self._initialize_fallback()
            else:
                logger.info(f"✅ Native TensorRT engines loaded: {list(self.engines.keys())}")

        except ImportError as e:
            logger.error(f"❌ TensorRT not available: {e}")
            self._initialize_fallback()
        except Exception as e:
            logger.error(f"❌ Engine initialization failed: {e}")
            self._initialize_fallback()

    def _load_engine(self, task: str, engine_filename: str, model_name: str):
        """Load a specific TensorRT engine"""
        try:
            engine_path = self.engines_dir / engine_filename
            metadata_path = self.engines_dir / (engine_filename.replace('.engine', '.json'))

            if not engine_path.exists():
                logger.warning(f"⚠️  {task} native engine not found: {engine_path}")
                return False

            # Load engine
            with open(engine_path, 'rb') as f:
                engine_data = f.read()

            engine = self.runtime.deserialize_cuda_engine(engine_data)
            if engine is None:
                logger.error(f"❌ Failed to deserialize {task} engine")
                return False

            # Create execution context
            context = engine.create_execution_context()
            if context is None:
                logger.error(f"❌ Failed to create {task} execution context")
                return False

            # Load metadata
            metadata = {}
            if metadata_path.exists():
                with open(metadata_path) as f:
                    metadata = json.load(f)

            # Load tokenizer
            try:
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.tokenizers[task] = tokenizer
            except Exception as e:
                logger.error(f"❌ Failed to load {task} tokenizer: {e}")
                return False

            # Store everything
            self.engines[task] = engine
            self.contexts[task] = context
            self.engine_metadata[task] = metadata

            logger.info(f"✅ {task} native engine loaded:")
            logger.info(f"   Max Batch Size: {metadata.get('max_batch_size', 'unknown')}")
            logger.info(f"   Precision: {metadata.get('precision', 'unknown').upper()}")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to load {task} engine: {e}")
            return False

    def _initialize_fallback(self):
        """Initialize fallback system when native engines unavailable"""
        try:
            self.fallback_analyst = GPUAcceleratedAnalyst()
            logger.info("✅ Fallback GPU analyst ready")
        except Exception as e:
            logger.error(f"❌ Fallback initialization failed: {e}")
            self.fallback_analyst = None

    def score_sentiment_native(self, text: str) -> float | None:
        """Ultra-fast native TensorRT sentiment scoring"""
        if 'sentiment' not in self.engines:
            return self._fallback_sentiment(text)

        start_time = time.time()

        try:
            result = self._run_native_inference(text, 'sentiment')

            if result is not None:
                # Process sentiment result (assuming [negative, neutral, positive])
                probabilities = self._softmax(result)
                score = float(probabilities[2])  # Positive probability

                processing_time = time.time() - start_time
                self.performance_stats['native_requests'] += 1
                self.performance_stats['native_time'] += processing_time

                logger.debug(f"⚡ Native sentiment: {score:.3f} ({processing_time*1000:.1f}ms)")
                return score
            else:
                return self._fallback_sentiment(text)

        except Exception as e:
            logger.error(f"❌ Native sentiment inference failed: {e}")
            return self._fallback_sentiment(text)

    def score_bias_native(self, text: str) -> float | None:
        """Ultra-fast native TensorRT bias scoring"""
        if 'bias' not in self.engines:
            return self._fallback_bias(text)

        start_time = time.time()

        try:
            result = self._run_native_inference(text, 'bias')

            if result is not None:
                # Process bias result (assuming [not_toxic, toxic])
                probabilities = self._softmax(result)
                score = float(probabilities[1])  # Toxic probability

                processing_time = time.time() - start_time
                self.performance_stats['native_requests'] += 1
                self.performance_stats['native_time'] += processing_time

                logger.debug(f"⚡ Native bias: {score:.3f} ({processing_time*1000:.1f}ms)")
                return score
            else:
                return self._fallback_bias(text)

        except Exception as e:
            logger.error(f"❌ Native bias inference failed: {e}")
            return self._fallback_bias(text)

    def score_sentiment_batch_native(self, texts: list[str]) -> list[float | None]:
        """Ultra-fast native TensorRT batch sentiment scoring"""
        if 'sentiment' not in self.engines or not texts:
            return self._fallback_sentiment_batch(texts)

        start_time = time.time()

        try:
            results = self._run_native_batch_inference(texts, 'sentiment')

            if results is not None:
                # Process batch sentiment results
                scores = []
                for result in results:
                    probabilities = self._softmax(result)
                    scores.append(float(probabilities[2]))  # Positive probability

                processing_time = time.time() - start_time
                self.performance_stats['native_requests'] += len(texts)
                self.performance_stats['native_time'] += processing_time

                articles_per_sec = len(texts) / processing_time
                logger.info(f"⚡ Native batch sentiment: {len(texts)} articles ({articles_per_sec:.1f} articles/sec)")

                return scores
            else:
                return self._fallback_sentiment_batch(texts)

        except Exception as e:
            logger.error(f"❌ Native batch sentiment inference failed: {e}")
            return self._fallback_sentiment_batch(texts)

    def score_bias_batch_native(self, texts: list[str]) -> list[float | None]:
        """Ultra-fast native TensorRT batch bias scoring"""
        if 'bias' not in self.engines or not texts:
            return self._fallback_bias_batch(texts)

        start_time = time.time()

        try:
            results = self._run_native_batch_inference(texts, 'bias')

            if results is not None:
                # Process batch bias results
                scores = []
                for result in results:
                    probabilities = self._softmax(result)
                    scores.append(float(probabilities[1]))  # Toxic probability

                processing_time = time.time() - start_time
                self.performance_stats['native_requests'] += len(texts)
                self.performance_stats['native_time'] += processing_time

                articles_per_sec = len(texts) / processing_time
                logger.info(f"⚡ Native batch bias: {len(texts)} articles ({articles_per_sec:.1f} articles/sec)")

                return scores
            else:
                return self._fallback_bias_batch(texts)

        except Exception as e:
            logger.error(f"❌ Native batch bias inference failed: {e}")
            return self._fallback_bias_batch(texts)

    def _run_native_inference(self, text: str, task: str) -> np.ndarray | None:
        """Run single inference on native TensorRT engine"""
        try:

            _engine = self.engines[task]
            context = self.contexts[task]
            tokenizer = self.tokenizers[task]
            metadata = self.engine_metadata[task]

            # Tokenize input - use correct metadata field name
            max_length = metadata.get('sequence_length', 512)
            encoded = tokenizer(
                text,
                truncation=True,
                padding='max_length',
                max_length=max_length,
                return_tensors='np'
            )

            input_ids = encoded['input_ids'].astype(np.int32)
            attention_mask = encoded['attention_mask'].astype(np.int32)

            # Check if this engine needs token_type_ids (bias model has input.3)
            needs_token_type_ids = 'input.3' in [self.engines[task].get_tensor_name(i)
                                                 for i in range(self.engines[task].num_io_tensors)]

            if needs_token_type_ids:
                # Create token_type_ids with fixed shape (1, max_length) for BERT - single inference
                token_type_ids = np.zeros((1, max_length), dtype=np.int32)
                context.set_input_shape('input.3', token_type_ids.shape)

            # Set dynamic input shapes using new API
            context.set_input_shape('input_ids', input_ids.shape)
            context.set_input_shape('attention_mask', attention_mask.shape)

            # Allocate GPU memory
            d_input_ids = cuda.mem_alloc(input_ids.nbytes)
            d_attention_mask = cuda.mem_alloc(attention_mask.nbytes)

            # Allocate GPU memory for token_type_ids if needed
            if needs_token_type_ids:
                d_token_type_ids = cuda.mem_alloc(token_type_ids.nbytes)

            # Output allocation
            num_classes = metadata.get('num_classes', 2)
            output_shape = (input_ids.shape[0], num_classes)
            output = np.empty(output_shape, dtype=np.float32)
            d_output = cuda.mem_alloc(output.nbytes)

            # Copy input to GPU with synchronization
            cuda.memcpy_htod(d_input_ids, input_ids)
            cuda.memcpy_htod(d_attention_mask, attention_mask)
            if needs_token_type_ids:
                cuda.memcpy_htod(d_token_type_ids, token_type_ids)

            # Ensure memory operations complete
            self.cuda_stream.synchronize()

            # Set tensor addresses using new API
            context.set_tensor_address('input_ids', int(d_input_ids))
            context.set_tensor_address('attention_mask', int(d_attention_mask))
            if needs_token_type_ids:
                context.set_tensor_address('input.3', int(d_token_type_ids))
            context.set_tensor_address('logits', int(d_output))

            # Run inference using new API with stream handle
            context.execute_async_v3(int(self.cuda_stream.handle))
            self.cuda_stream.synchronize()

            # Copy result back
            cuda.memcpy_dtoh(output, d_output)

            return output[0]  # Return single result

        except Exception as e:
            logger.error(f"❌ Native inference failed for {task}: {e}")
            return None

    def _run_native_batch_inference(self, texts: list[str], task: str) -> list[np.ndarray] | None:
        """Run batch inference on native TensorRT engine"""
        try:

            batch_size = len(texts)
            if batch_size == 0:
                return []

            _engine = self.engines[task]
            context = self.contexts[task]
            tokenizer = self.tokenizers[task]
            metadata = self.engine_metadata[task]

            # Check batch size limit
            max_batch = metadata.get('max_batch_size', 100)
            if batch_size > max_batch:
                logger.warning(f"⚠️  Batch size {batch_size} exceeds max {max_batch}, splitting")
                # Process in chunks
                chunk_size = max_batch
                all_results = []
                for i in range(0, batch_size, chunk_size):
                    chunk = texts[i:i + chunk_size]
                    chunk_results = self._run_native_batch_inference(chunk, task)
                    if chunk_results:
                        all_results.extend(chunk_results)
                    else:
                        return None
                return all_results

            # Tokenize batch - use correct metadata field name
            max_length = metadata.get('sequence_length', 512)
            encoded = tokenizer(
                texts,
                truncation=True,
                padding='max_length',
                max_length=max_length,
                return_tensors='np'
            )

            input_ids = encoded['input_ids'].astype(np.int32)
            attention_mask = encoded['attention_mask'].astype(np.int32)

            # Check if this engine needs token_type_ids (bias model has input.3)
            needs_token_type_ids = 'input.3' in [self.engines[task].get_tensor_name(i)
                                                 for i in range(self.engines[task].num_io_tensors)]

            if needs_token_type_ids:
                # Create token_type_ids with fixed shape (1, max_length) for BERT - batch processing
                token_type_ids = np.zeros((1, max_length), dtype=np.int32)
                context.set_input_shape('input.3', token_type_ids.shape)

            # Set dynamic batch shapes using new API
            context.set_input_shape('input_ids', input_ids.shape)
            context.set_input_shape('attention_mask', attention_mask.shape)

            # Allocate GPU memory for batch
            d_input_ids = cuda.mem_alloc(input_ids.nbytes)
            d_attention_mask = cuda.mem_alloc(attention_mask.nbytes)

            # Allocate GPU memory for token_type_ids if needed
            if needs_token_type_ids:
                d_token_type_ids = cuda.mem_alloc(token_type_ids.nbytes)

            # Output allocation for batch
            num_classes = metadata.get('num_classes', 2)
            output_shape = (batch_size, num_classes)
            output = np.empty(output_shape, dtype=np.float32)
            d_output = cuda.mem_alloc(output.nbytes)

            # Copy batch input to GPU with synchronization
            cuda.memcpy_htod(d_input_ids, input_ids)
            cuda.memcpy_htod(d_attention_mask, attention_mask)
            if needs_token_type_ids:
                cuda.memcpy_htod(d_token_type_ids, token_type_ids)

            # Ensure memory operations complete
            self.cuda_stream.synchronize()

            # Set tensor addresses using new API
            context.set_tensor_address('input_ids', int(d_input_ids))
            context.set_tensor_address('attention_mask', int(d_attention_mask))
            if needs_token_type_ids:
                context.set_tensor_address('input.3', int(d_token_type_ids))
            context.set_tensor_address('logits', int(d_output))

            # Run batch inference using new API with stream handle
            context.execute_async_v3(int(self.cuda_stream.handle))
            self.cuda_stream.synchronize()

            # Copy batch results back
            cuda.memcpy_dtoh(output, d_output)

            # Return list of individual results
            return [output[i] for i in range(batch_size)]

        except Exception as e:
            logger.error(f"❌ Native batch inference failed for {task}: {e}")
            return None

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Apply softmax activation to get probabilities"""
        exp_x = np.exp(x - np.max(x))
        return exp_x / np.sum(exp_x)

    def _fallback_sentiment(self, text: str) -> float | None:
        """Fallback sentiment scoring"""
        if self.fallback_analyst and hasattr(self.fallback_analyst, 'score_sentiment_gpu'):
            start_time = time.time()
            result = self.fallback_analyst.score_sentiment_gpu(text)
            processing_time = time.time() - start_time

            self.performance_stats['fallback_requests'] += 1
            self.performance_stats['fallback_time'] += processing_time

            return result
        return None

    def _fallback_bias(self, text: str) -> float | None:
        """Fallback bias scoring"""
        if self.fallback_analyst and hasattr(self.fallback_analyst, 'score_bias_gpu'):
            start_time = time.time()
            result = self.fallback_analyst.score_bias_gpu(text)
            processing_time = time.time() - start_time

            self.performance_stats['fallback_requests'] += 1
            self.performance_stats['fallback_time'] += processing_time

            return result
        return None

    def _fallback_sentiment_batch(self, texts: list[str]) -> list[float | None]:
        """Fallback batch sentiment scoring"""
        if self.fallback_analyst and hasattr(self.fallback_analyst, 'score_sentiment_batch_gpu'):
            start_time = time.time()
            results = self.fallback_analyst.score_sentiment_batch_gpu(texts)
            processing_time = time.time() - start_time

            self.performance_stats['fallback_requests'] += len(texts)
            self.performance_stats['fallback_time'] += processing_time

            return results
        return [None] * len(texts)

    def _fallback_bias_batch(self, texts: list[str]) -> list[float | None]:
        """Fallback batch bias scoring"""
        if self.fallback_analyst and hasattr(self.fallback_analyst, 'score_bias_batch_gpu'):
            start_time = time.time()
            results = self.fallback_analyst.score_bias_batch_gpu(texts)
            processing_time = time.time() - start_time

            self.performance_stats['fallback_requests'] += len(texts)
            self.performance_stats['fallback_time'] += processing_time

            return results
        return [None] * len(texts)

    def get_performance_stats(self) -> dict[str, Any]:
        """Get comprehensive performance statistics"""
        stats = self.performance_stats.copy()

        # Calculate native performance
        if stats['native_requests'] > 0:
            stats['native_avg_time'] = stats['native_time'] / stats['native_requests']
            stats['native_articles_per_sec'] = stats['native_requests'] / stats['native_time']

        # Calculate fallback performance
        if stats['fallback_requests'] > 0:
            stats['fallback_avg_time'] = stats['fallback_time'] / stats['fallback_requests']
            stats['fallback_articles_per_sec'] = stats['fallback_requests'] / stats['fallback_time']

        # Calculate improvement factor
        if stats.get('native_articles_per_sec', 0) > 0:
            baseline = 151.4  # Production baseline
            stats['improvement_factor'] = stats['native_articles_per_sec'] / baseline
            stats['target_achieved'] = stats['improvement_factor'] >= 2.0

        return stats

    def get_engine_info(self) -> dict[str, dict[str, Any]]:
        """Get information about loaded engines"""
        info = {}
        for task, metadata in self.engine_metadata.items():
            info[task] = {
                'loaded': task in self.engines,
                'metadata': metadata,
                'engine_path': str(self.engines_dir / f"native_{task}_*.engine")
            }
        return info

    # Wrapper methods for backward compatibility
    def score_sentiment(self, text: str) -> float | None:
        """Wrapper for score_sentiment_native for backward compatibility"""
        return self.score_sentiment_native(text)

    def score_bias(self, text: str) -> float | None:
        """Wrapper for score_bias_native for backward compatibility"""
        return self.score_bias_native(text)

    def score_sentiment_batch(self, texts: list[str]) -> list[float | None]:
        """Wrapper for score_sentiment_batch_native for backward compatibility"""
        return self.score_sentiment_batch_native(texts)

    def score_bias_batch(self, texts: list[str]) -> list[float | None]:
        """Wrapper for score_bias_batch_native for backward compatibility"""
        return self.score_bias_batch_native(texts)

    def cleanup(self):
        """Properly cleanup CUDA context and resources"""
        try:
            # Check if Python is shutting down
            if hasattr(sys, 'meta_path') and sys.meta_path is None:
                logger.info("✅ Skipping CUDA cleanup during Python shutdown")
                return

            if hasattr(self, 'context_created') and self.context_created and hasattr(self, 'cuda_context'):
                # Only cleanup if we created the context and it's still current
                if self.cuda_context is not None:
                    try:
                        # Check if this context is current before popping
                        current_context = cuda.Context.get_current()
                        if current_context is not None and current_context.handle == self.cuda_context.handle:
                            self.cuda_context.pop()
                            logger.info("✅ CUDA context properly cleaned up")
                        else:
                            # Context is not current, just detach
                            self.cuda_context.detach()
                            logger.info("✅ CUDA context detached (was not current)")
                    except cuda.LogicError as e:
                        # Context might already be cleaned up
                        logger.info(f"✅ CUDA context cleanup skipped: {e}")
                    except Exception as e:
                        # Handle any other cleanup errors gracefully
                        logger.info(f"✅ CUDA context cleanup completed with note: {e}")
                    finally:
                        self.cuda_context = None
                        self.context_created = False
        except Exception as e:
            logger.warning(f"⚠️ Context cleanup warning: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def __del__(self):
        """Destructor to ensure cleanup"""
        try:
            self.cleanup()
        except Exception:
            pass  # Ignore errors during destruction


# Global native engine instance
_native_engine = None

def get_native_engine():
    """Get or create the native TensorRT engine instance"""
    global _native_engine
    if _native_engine is None:
        _native_engine = NativeTensorRTInferenceEngine()
    return _native_engine


# High-level API functions
def score_sentiment_native(text: str) -> float:
    """Ultra-fast native TensorRT sentiment scoring"""
    engine = get_native_engine()
    return engine.score_sentiment_native(text)

def score_bias_native(text: str) -> float:
    """Ultra-fast native TensorRT bias scoring"""
    engine = get_native_engine()
    return engine.score_bias_native(text)

def score_sentiment_batch_native(texts: list[str]) -> list[float | None]:
    """Ultra-fast native TensorRT batch sentiment scoring"""
    engine = get_native_engine()
    return engine.score_sentiment_batch_native(texts)

def score_bias_batch_native(texts: list[str]) -> list[float | None]:
    """Ultra-fast native TensorRT batch bias scoring"""
    engine = get_native_engine()
    return engine.score_bias_batch_native(texts)


if __name__ == "__main__":
    # Test native TensorRT engine
    print("⚡ Testing Native TensorRT Inference Engine")

    engine = NativeTensorRTInferenceEngine()

    # Show engine info
    engine_info = engine.get_engine_info()
    print("\n📊 Engine Status:")
    for task, info in engine_info.items():
        status = "✅ LOADED" if info['loaded'] else "❌ NOT FOUND"
        print(f"  {task.capitalize()}: {status}")

    # Test inference
    test_text = "This is fantastic news about the market performing exceptionally well today!"

    print(f"\n🧪 Test Article: {test_text[:60]}...")

    # Single inference
    sentiment = engine.score_sentiment_native(test_text)
    bias = engine.score_bias_native(test_text)

    print(f"⚡ Native Sentiment: {sentiment}")
    print(f"⚡ Native Bias: {bias}")

    # Batch inference
    test_batch = [test_text] * 25
    print(f"\n🚀 Testing batch inference ({len(test_batch)} articles):")

    batch_sentiments = engine.score_sentiment_batch_native(test_batch)
    batch_bias = engine.score_bias_batch_native(test_batch)

    print("✅ Batch completed successfully")

    # Performance stats
    stats = engine.get_performance_stats()
    print("\n📈 Performance Stats:")
    print(f"  Native Requests: {stats.get('native_requests', 0)}")
    print(f"  Fallback Requests: {stats.get('fallback_requests', 0)}")

    if stats.get('native_articles_per_sec', 0) > 0:
        print(f"  Native Speed: {stats['native_articles_per_sec']:.1f} articles/sec")
        print(f"  Improvement: {stats.get('improvement_factor', 0):.2f}x baseline")

        if stats.get('target_achieved', False):
            print("🎉 TARGET ACHIEVED: 2x+ performance improvement!")
        else:
            print("🎯 Still optimizing toward 2-4x target")

    print("\n⚡ Native TensorRT engine test complete!")
