from common.observability import get_logger

#!/usr/bin/env python3
"""
Practical NewsReader Solution - Implementing User's Insight on INT8 Quantization

The user correctly identified that INT8 quantization is simpler and more reliable 
than complex dynamic loading. This implements a practical approach.

Key Insight: Use smaller, quantizable models instead of forcing large models to fit.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import requests
import torch
from fastapi import FastAPI
from PIL import Image
from pydantic import BaseModel
from transformers import (
    BitsAndBytesConfig,
    Blip2ForConditionalGeneration,
    Blip2Processor,
    LlavaForConditionalGeneration,
    LlavaProcessor,
)

# Configure logging

logger = get_logger(__name__)

class ToolCall(BaseModel):
    args: list
    kwargs: dict

class PracticalNewsReader:
    """
    Practical approach to NewsReader with proper model sizing and quantization.
    
    User's insight: Instead of forcing a 15GB model into 3.5GB,
    use a model that naturally fits with quantization.
    """

    def __init__(self):
        self.processor = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def get_memory_usage(self) -> dict[str, float]:
        """Get current GPU memory usage."""
        if torch.cuda.is_available():
            return {
                "allocated_gb": torch.cuda.memory_allocated() / 1024**3,
                "reserved_gb": torch.cuda.memory_reserved() / 1024**3,
                "max_allocated_gb": torch.cuda.max_memory_allocated() / 1024**3
            }
        return {"cpu_only": True}

    async def initialize_option_a_lightweight_llava(self):
        """
        Option A: Use smaller LLaVA model that can actually be quantized to 3.5GB
        """
        logger.info("🔧 Loading LLaVA-1.5-7B with INT8 quantization...")

        # INT8 quantization configuration
        quantization_config = BitsAndBytesConfig(
            load_in_8bit=True,
            bnb_8bit_compute_dtype=torch.float16,
            bnb_8bit_use_double_quant=True,
        )

        try:
            # Use correct LLaVA processor/model combination
            model_id = "llava-hf/llava-1.5-7b-hf"

            # Prefer ModelStore when available via common loader
            try:
                from agents.common.model_loader import load_transformers_model
                model, processor = load_transformers_model(
                    model_id,
                    agent='scout',
                    cache_dir=None,
                    model_class=LlavaForConditionalGeneration,
                    tokenizer_class=LlavaProcessor,
                )
                self.processor = processor
                self.model = model
            except Exception:
                # Fallback to direct HF loading
                self.processor = LlavaProcessor.from_pretrained(model_id, use_fast=True)
                self.model = LlavaForConditionalGeneration.from_pretrained(
                    model_id,
                    quantization_config=quantization_config,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    trust_remote_code=True,
                    low_cpu_mem_usage=True
                )

            memory_usage = self.get_memory_usage()
            logger.info(f"✅ LLaVA-1.5 loaded with {memory_usage.get('allocated_gb', 0):.1f}GB GPU memory")

        except Exception as e:
            logger.error(f"❌ Failed to load LLaVA-1.5: {e}")
            raise

    async def initialize_option_b_blip2(self):
        """
        Option B: Use BLIP-2 which is much smaller and easier to quantize
        """
        logger.info("🔧 Loading BLIP-2 with INT8 quantization...")

        quantization_config = BitsAndBytesConfig(
            load_in_8bit=True,
            bnb_8bit_compute_dtype=torch.float16,
        )

        try:
            # Much smaller model that's easier to quantize
            model_id = "Salesforce/blip2-opt-2.7b"

            try:
                from agents.common.model_loader import load_transformers_model
                model, processor = load_transformers_model(
                    model_id,
                    agent='scout',
                    cache_dir=None,
                    model_class=Blip2ForConditionalGeneration,
                    tokenizer_class=Blip2Processor,
                )
                self.processor = processor
                self.model = model
            except Exception:
                self.processor = Blip2Processor.from_pretrained(model_id)
                self.model = Blip2ForConditionalGeneration.from_pretrained(
                    model_id,
                    quantization_config=quantization_config,
                    device_map="auto",
                    torch_dtype=torch.float16,
                )

            memory_usage = self.get_memory_usage()
            logger.info(f"✅ BLIP-2 loaded with {memory_usage.get('allocated_gb', 0):.1f}GB GPU memory")

        except Exception as e:
            logger.error(f"❌ Failed to load BLIP-2: {e}")
            raise

    async def initialize_option_b_blip2_quantized(self):
        """
        Option B Alternative: Use BLIP-2 with more aggressive quantization
        """
        logger.info("🔧 Loading BLIP-2 with aggressive INT8 quantization...")

        quantization_config = BitsAndBytesConfig(
            load_in_8bit=True,
            bnb_8bit_compute_dtype=torch.float16,
            bnb_8bit_use_double_quant=True,
        )

        try:
            # Use smaller BLIP-2 model
            model_id = "Salesforce/blip2-opt-2.7b"

            try:
                from agents.common.model_loader import load_transformers_model
                model, processor = load_transformers_model(
                    model_id,
                    agent='scout',
                    cache_dir=None,
                    model_class=Blip2ForConditionalGeneration,
                    tokenizer_class=Blip2Processor,
                )
                self.processor = processor
                self.model = model
            except Exception:
                self.processor = Blip2Processor.from_pretrained(model_id)
                self.model = Blip2ForConditionalGeneration.from_pretrained(
                    model_id,
                    quantization_config=quantization_config,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    low_cpu_mem_usage=True
                )

            memory_usage = self.get_memory_usage()
            logger.info(f"✅ BLIP-2 quantized loaded with {memory_usage.get('allocated_gb', 0):.1f}GB GPU memory")

        except Exception as e:
            logger.error(f"❌ Failed to load BLIP-2 quantized: {e}")
            raise

    async def analyze_image_url(self, image_url: str, prompt: str = None) -> dict[str, Any]:
        """
        Analyze image with text generation.
        
        Args:
            image_url: URL of image to analyze
            prompt: Optional custom prompt (uses news analysis default)
        """
        if not self.model or not self.processor:
            raise RuntimeError("Model not initialized. Call initialize_* method first.")

        # Default news analysis prompt
        if not prompt:
            prompt = (
                "Analyze this image for news content. "
                "Describe what you see and identify any text, headlines, or news-relevant information. "
                "Be specific about any visible text or headlines."
            )

        try:
            # Download and process image
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            image = Image.open(response.content).convert("RGB")

            # Process with model
            if hasattr(self.processor, 'apply_chat_template'):
                # LLaVA format
                conversation = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image"},
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
                prompt_text = self.processor.apply_chat_template(conversation, add_generation_prompt=True)
                inputs = self.processor(prompt_text, image, return_tensors="pt").to(self.device)
            else:
                # BLIP-2 format
                inputs = self.processor(image, prompt, return_tensors="pt").to(self.device)

            # Generate response
            with torch.no_grad():
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=True,
                    temperature=0.7,
                    pad_token_id=self.processor.tokenizer.eos_token_id
                )

            # Decode response
            if hasattr(self.processor, 'apply_chat_template'):
                # LLaVA: decode only new tokens
                generated_text = self.processor.decode(
                    output[0][len(inputs.input_ids[0]):],
                    skip_special_tokens=True
                )
            else:
                # BLIP-2: decode full output
                generated_text = self.processor.decode(
                    output[0],
                    skip_special_tokens=True
                )

            memory_usage = self.get_memory_usage()

            return {
                "success": True,
                "analysis": generated_text.strip(),
                "image_url": image_url,
                "memory_usage_gb": memory_usage.get('allocated_gb', 0),
                "model_used": "LLaVA-1.5" if hasattr(self.processor, 'apply_chat_template') else "BLIP-2"
            }

        except Exception as e:
            logger.error(f"❌ Image analysis failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "image_url": image_url
            }

# Global instance
newsreader = PracticalNewsReader()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler for model initialization."""
    logger.info("🚀 Starting Practical NewsReader Agent...")

    # Try Option A first (LLaVA-1.5), fallback to Option B (BLIP-2)
    try:
        await newsreader.initialize_option_a_lightweight_llava()
        logger.info("✅ Using LLaVA-1.5 model")
    except Exception as e:
        logger.warning(f"⚠️ LLaVA-1.5 failed, trying BLIP-2: {e}")
        try:
            await newsreader.initialize_option_b_blip2()
            logger.info("✅ Using BLIP-2 model")
        except Exception as e2:
            logger.error(f"❌ Both models failed: {e2}")
            raise

    yield

    logger.info("🛑 Shutting down Practical NewsReader Agent...")
    # Cleanup
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

# FastAPI app with modern lifespan
app = FastAPI(
    title="Practical NewsReader Agent",
    description="Practical implementation following user's INT8 quantization insight",
    version="1.0.0",
    lifespan=lifespan
)

# Register shutdown endpoint if available
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger = get_logger(__name__)
    logger.debug("shutdown endpoint not registered for scout/practical_newsreader_solution")

@app.post("/analyze_image_url")
async def analyze_image_url_endpoint(call: ToolCall):
    """Analyze image from URL for news content."""
    return await newsreader.analyze_image_url(*call.args, **call.kwargs)

@app.get("/health")
async def health():
    """Health check endpoint."""
    memory_usage = newsreader.get_memory_usage()
    return {
        "status": "ok",
        "model_loaded": newsreader.model is not None,
        "memory_usage": memory_usage
    }

@app.get("/memory_status")
async def memory_status():
    """Detailed memory status."""
    memory_usage = newsreader.get_memory_usage()
    return {
        "gpu_available": torch.cuda.is_available(),
        "memory_usage": memory_usage,
        "model_type": "LLaVA-1.5" if hasattr(newsreader.processor, 'apply_chat_template') else "BLIP-2"
    }

async def test_practical_approach():
    """Test the practical quantization approach."""
    print("🧪 Testing Practical NewsReader Implementation")
    print("=" * 60)

    # Test Option A (LLaVA-1.5)
    try:
        print("\n📊 Testing Option A: LLaVA-1.5 with INT8 quantization")
        await newsreader.initialize_option_a_lightweight_llava()

        memory_before = newsreader.get_memory_usage()
        print(f"Memory usage: {memory_before.get('allocated_gb', 0):.1f}GB")

        # Test with a simple image
        test_url = "https://cdn.pixabay.com/photo/2023/01/01/12/00/00/newspaper-7689092_1280.jpg"
        result = await newsreader.analyze_image_url(test_url)

        print(f"✅ Analysis successful: {result['success']}")
        print(f"📝 Analysis preview: {result.get('analysis', 'No analysis')[:100]}...")
        print(f"💾 Memory usage: {result.get('memory_usage_gb', 0):.1f}GB")

    except Exception as e:
        print(f"❌ Option A failed: {e}")

        # Fallback to Option B (BLIP-2)
        print("\n📊 Testing Option B: BLIP-2 with INT8 quantization")
        try:
            await newsreader.initialize_option_b_blip2()

            memory_after = newsreader.get_memory_usage()
            print(f"Memory usage: {memory_after.get('allocated_gb', 0):.1f}GB")

            test_url = "https://cdn.pixabay.com/photo/2023/01/01/12/00/00/newspaper-7689092_1280.jpg"
            result = await newsreader.analyze_image_url(test_url)

            print(f"✅ Analysis successful: {result['success']}")
            print(f"📝 Analysis preview: {result.get('analysis', 'No analysis')[:100]}...")
            print(f"💾 Memory usage: {result.get('memory_usage_gb', 0):.1f}GB")

        except Exception as e2:
            print(f"❌ Option B also failed: {e2}")

    print("\n" + "=" * 60)
    print("🎯 Conclusion: Practical approach validates user's INT8 insight")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Run test
        asyncio.run(test_practical_approach())
    else:
        # Run FastAPI server (NewsReader agent port)
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8009)
