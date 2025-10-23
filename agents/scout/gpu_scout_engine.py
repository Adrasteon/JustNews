 """
GPU-Accelerated Scout Agent Engine with LLaMA-3-8B Intelligence
Production-ready content pre-filtering and classification system
"""

import json
import os
import re
from datetime import datetime, timezone

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    pipeline,
)

from common.observability import get_logger

logger = get_logger(__name__)

class GPUScoutInferenceEngine:
    """
    Production-ready Scout agent with LLaMA-3-8B intelligence for content pre-filtering
    
    Features:
    - News vs non-news classification
    - Content quality assessment  
    - Bias detection and flagging
    - Source credibility scoring
    - Batch processing for efficiency
    - GPU acceleration with FP16 precision
    """

    def __init__(self, model_path: str | None = None):
        # Default to env-configurable conversational model; DialoGPT (deprecated) is deprecated.
        self.model_path = model_path or os.environ.get("SCOUT_CONVERSATIONAL_MODEL", "distilgpt2")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.tokenizer = None
        self.classification_pipeline = None

        # Initialize models
        self._initialize_models()

        # Content classification prompts
        self.classification_prompts = {
            "news_detection": """
Analyze the following content and determine if it is legitimate news content.

Content: {content}

Respond with JSON format:
{
    "is_news": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "explanation",
    "content_type": "news|opinion|forum|advertisement|social_media|other"
}
""",
            "quality_assessment": """
Assess the quality of this news content on multiple dimensions.

Content: {content}

Respond with JSON format:
{
    "overall_quality": 0.0-1.0,
    "factual_content": 0.0-1.0,
    "source_credibility": 0.0-1.0,
    "writing_quality": 0.0-1.0,
    "completeness": 0.0-1.0,
    "reasoning": "detailed explanation"
}
""",
            "bias_detection": """
Analyze this content for political, ideological, or commercial bias.

Content: {content}

Respond with JSON format:
{
    "bias_score": 0.0-1.0,
    "bias_type": "political|commercial|ideological|none",
    "bias_direction": "left|right|center|pro|anti|neutral",
    "bias_indicators": ["list of specific bias indicators found"],
    "confidence": 0.0-1.0
}
"""
        }

    def _initialize_models(self):
        """Initialize LLaMA-3-8B model with GPU optimization"""
        try:
            logger.info(f"🔄 Loading Scout model on {self.device}...")

            # Check for internet connectivity
            try:
                import requests
                requests.get("https://huggingface.co", timeout=5)
                use_offline = False
            except Exception:
                logger.warning("No internet connection - using offline mode")
                use_offline = True
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_DATASETS_OFFLINE"] = "1"

            # Quantization config for memory efficiency - UPDATED TO FP4
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="fp4"  # UPDATED: FP4 instead of NF4
            )

            # Load tokenizer with ModelStore-aware loader and fallback
            try:
                from agents.common.model_loader import load_transformers_model
                model_obj, tokenizer_obj = load_transformers_model(
                    self.model_path,
                    agent='scout',
                    cache_dir=None,
                    model_class=None,
                    tokenizer_class=AutoTokenizer,
                )
                self.tokenizer = tokenizer_obj
            except Exception as e:
                logger.warning(f"Failed to load tokenizer via ModelStore/loader: {e}; trying HF fallback")
                try:
                    self.tokenizer = AutoTokenizer.from_pretrained(
                        self.model_path,
                        trust_remote_code=True,
                        padding_side="left",
                        local_files_only=use_offline
                    )
                except Exception as e2:
                    logger.warning(f"Failed to load {self.model_path}, trying GPT-2 fallback: {e2}")
                    self.model_path = "gpt2"
                    self.tokenizer = AutoTokenizer.from_pretrained(
                        self.model_path,
                        trust_remote_code=True,
                        padding_side="left",
                        local_files_only=use_offline
                    )

            if self.tokenizer.pad_token is None:  # type: ignore
                self.tokenizer.pad_token = self.tokenizer.eos_token  # type: ignore

            # Load model with GPU optimization
                # Load model using ModelStore-aware loader with explicit class when possible
                try:
                    from agents.common.model_loader import load_transformers_model
                    model_obj, tokenizer_obj = load_transformers_model(
                        self.model_path,
                        agent='scout',
                        cache_dir=None,
                        model_class=AutoModelForCausalLM,
                        tokenizer_class=AutoTokenizer,
                    )
                    self.model = model_obj
                except Exception as e:
                    logger.warning(f"Failed to load model via ModelStore/loader: {e}; trying HF fallback")
                    try:
                        if self.device == "cuda":
                            self.model = AutoModelForCausalLM.from_pretrained(
                                self.model_path,
                                quantization_config=quantization_config if not use_offline else None,
                                device_map="auto",
                                torch_dtype=torch.float16,
                                trust_remote_code=True,
                                local_files_only=use_offline
                            )
                        else:
                            self.model = AutoModelForCausalLM.from_pretrained(
                                self.model_path,
                                torch_dtype=torch.float32,
                                trust_remote_code=True,
                                local_files_only=use_offline
                            )
                    except Exception as e2:
                        logger.error(f"❌ Failed to initialize model after fallbacks: {e2}")
                        self.model = None

                # Create pipeline for batch processing
                self.classification_pipeline = pipeline(  # type: ignore
                    "text-generation",
                    model=self.model,  # type: ignore
                    tokenizer=self.tokenizer,  # type: ignore
                    batch_size=4 if self.device == "cuda" else 1,
                    max_new_tokens=512,
                    do_sample=True,
                    temperature=0.1,
                    top_p=0.9
                )

                logger.info(f"✅ Scout model loaded successfully on {self.device}")
            else:
                # CPU fallback
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float32,
                    trust_remote_code=True,
                    local_files_only=use_offline
                )

                self.classification_pipeline = pipeline(  # type: ignore
                    "text-generation",
                    model=self.model,  # type: ignore
                    tokenizer=self.tokenizer,  # type: ignore
                    max_new_tokens=512,
                    do_sample=True,
                    temperature=0.1
                )

                logger.info("✅ Scout model loaded successfully on CPU")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Scout model: {e}")
            # Set up a fallback mode without AI
            self.model = None
            self.tokenizer = None
            self.classification_pipeline = None
            logger.warning("⚠️ Scout will run in heuristic-only mode")

    def classify_news_content(self, text: str, url: str | None = None) -> dict:
        """GPU-accelerated news content classification with intelligent fallback"""
        try:
            # Since GPT-2/DialoGPT (deprecated) isn't great for structured output,
            # prioritize our enhanced heuristic system which is working well
            logger.info("Using enhanced heuristic classification (primary)")
            result = self._heuristic_news_classification(text, url)

            # Only try AI enhancement for borderline cases
            if result.get('confidence', 0) < 0.7 and self.model is not None:
                try:
                    # Simple binary classification prompt
                    simple_prompt = f"Is this news content? Content: {text[:300]}... Answer: "

                    inputs = self.tokenizer(simple_prompt, return_tensors="pt",  # type: ignore
                                          truncation=True, max_length=256)
                    inputs = {k: v.to(self.device) for k, v in inputs.items()}

                    with torch.no_grad():
                        outputs = self.model.generate(  # type: ignore
                            **inputs,
                            max_new_tokens=10,  # Very short response
                            temperature=0.1,    # Low randomness
                            pad_token_id=self.tokenizer.eos_token_id,  # type: ignore
                            do_sample=True
                        )

                    ai_response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)  # type: ignore
                    ai_response = ai_response[len(simple_prompt):].strip().lower()

                    # AI enhancement for borderline cases
                    if any(word in ai_response for word in ['yes', 'true', 'news']):
                        if result.get('confidence', 0) < 0.6:
                            result['confidence'] = min(result.get('confidence', 0) + 0.2, 0.8)
                            result['reasoning'] += ' + AI confirmation'
                            logger.debug("✅ AI provided positive confirmation")
                    elif any(word in ai_response for word in ['no', 'false', 'not']):
                        if result.get('confidence', 0) > 0.4:
                            result['confidence'] = max(result.get('confidence', 0) - 0.2, 0.2)
                            result['reasoning'] += ' + AI disagreement'
                            logger.debug("✅ AI provided negative confirmation")

                    # Re-evaluate is_news based on updated confidence
                    result['is_news'] = result.get('confidence', 0) > 0.5

                except Exception as e:
                    logger.debug(f"AI enhancement failed: {e}")

            logger.debug(f"✅ Final classification: {result}")
            return result

        except Exception as e:
            logger.error(f"Classification error: {e}")
            # Ultimate fallback
            return {
                "is_news": any(keyword in text.lower() for keyword in ['news', 'breaking', 'reported', 'announced']),
                "confidence": 0.3,
                "content_type": "unknown",
                "reasoning": f"Emergency fallback due to error: {str(e)}",
                "method": "emergency_fallback"
            }

    def _heuristic_news_classification(self, content: str, url: str | None = None) -> dict:
        """
        Fallback heuristic-based news classification when AI is not available
        """
        news_score = 0.0
        reasoning_parts = []

        # Keywords that strongly indicate news content
        strong_news_keywords = [
            'breaking', 'reported', 'according to', 'spokesperson', 'statement',
            'announced', 'confirmed', 'arrested', 'charged', 'court', 'police',
            'government', 'minister', 'mp', 'council', 'investigation'
        ]

        # Keywords that moderately indicate news
        moderate_news_keywords = [
            'said', 'told', 'reports', 'news', 'today', 'yesterday',
            'this morning', 'this afternoon', 'sources', 'officials'
        ]

        # Non-news indicators
        non_news_keywords = [
            'buy now', 'click here', 'subscribe', 'advertisement', 'sponsored',
            'recipe', 'how to', 'guide', 'tutorial', 'review', 'opinion'
        ]

        content_lower = content.lower()

        # Check for strong news indicators
        strong_matches = sum(1 for keyword in strong_news_keywords if keyword in content_lower)
        if strong_matches > 0:
            news_score += strong_matches * 0.3
            reasoning_parts.append(f"Strong news keywords: {strong_matches}")

        # Check for moderate news indicators
        moderate_matches = sum(1 for keyword in moderate_news_keywords if keyword in content_lower)
        if moderate_matches > 0:
            news_score += moderate_matches * 0.1
            reasoning_parts.append(f"Moderate news keywords: {moderate_matches}")

        # Check for non-news indicators (negative score)
        non_news_matches = sum(1 for keyword in non_news_keywords if keyword in content_lower)
        if non_news_matches > 0:
            news_score -= non_news_matches * 0.2
            reasoning_parts.append(f"Non-news keywords: {non_news_matches}")

        # URL analysis
        if url:
            url_lower = url.lower()
            if any(indicator in url_lower for indicator in ['news', 'article', 'breaking']):
                news_score += 0.2
                reasoning_parts.append("News URL pattern")
            if any(indicator in url_lower for indicator in ['shop', 'buy', 'product']):
                news_score -= 0.3
                reasoning_parts.append("Commercial URL pattern")

        # Content length heuristic
        if len(content) > 500:
            news_score += 0.1
            reasoning_parts.append("Substantial content length")

        # Normalize score to 0-1 range
        confidence = max(0.0, min(1.0, news_score))
        is_news = confidence > 0.5

        return {
            "is_news": is_news,
            "confidence": confidence,
            "reasoning": "; ".join(reasoning_parts) if reasoning_parts else "Heuristic analysis",
            "content_type": "news" if is_news else "non-news",
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content_length": len(content),
            "method": "heuristic_classification"
        }

    def assess_content_quality(self, content: str, url: str | None = None) -> dict:
        """
        Assess content quality across multiple dimensions
        """
        try:
            prompt = self.classification_prompts["quality_assessment"].format(content=content[:2000])

            response = self.classification_pipeline(  # type: ignore
                prompt,
                max_new_tokens=256,
                do_sample=True,
                temperature=0.1
            )

            generated_text = response[0]['generated_text'][len(prompt):].strip()
            quality_assessment = self._extract_json_response(generated_text)

            # Add metadata
            quality_assessment["url"] = url
            quality_assessment["timestamp"] = datetime.now(timezone.utc).isoformat()
            quality_assessment["content_length"] = len(content)

            return quality_assessment

        except Exception as e:
            logger.error(f"❌ Quality assessment failed: {e}")
            return {
                "overall_quality": 0.0,
                "factual_content": 0.0,
                "source_credibility": 0.0,
                "writing_quality": 0.0,
                "completeness": 0.0,
                "reasoning": f"Assessment error: {str(e)}",
                "url": url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def detect_bias(self, content: str, url: str | None = None) -> dict:
        """
        Detect and analyze bias in content
        """
        try:
            prompt = self.classification_prompts["bias_detection"].format(content=content[:2000])

            response = self.classification_pipeline(  # type: ignore
                prompt,
                max_new_tokens=256,
                do_sample=True,
                temperature=0.1
            )

            generated_text = response[0]['generated_text'][len(prompt):].strip()
            bias_analysis = self._extract_json_response(generated_text)

            # Add metadata
            bias_analysis["url"] = url
            bias_analysis["timestamp"] = datetime.now(timezone.utc).isoformat()
            bias_analysis["content_length"] = len(content)

            return bias_analysis

        except Exception as e:
            logger.error(f"❌ Bias detection failed: {e}")
            return {
                "bias_score": 0.5,
                "bias_type": "unknown",
                "bias_direction": "unknown",
                "bias_indicators": [],
                "confidence": 0.0,
                "url": url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def comprehensive_content_analysis(self, content: str, url: str | None = None) -> dict:
        """
        Perform comprehensive analysis combining all Scout capabilities
        """
        try:
            logger.info(f"🔍 Performing comprehensive analysis for: {url}")

            # Run all analyses
            news_classification = self.classify_news_content(content, url)
            quality_assessment = self.assess_content_quality(content, url)
            bias_analysis = self.detect_bias(content, url)

            # Calculate overall Scout score
            overall_score = self._calculate_scout_score(
                news_classification, quality_assessment, bias_analysis
            )

            comprehensive_analysis = {
                "scout_score": overall_score,
                "news_classification": news_classification,
                "quality_assessment": quality_assessment,
                "bias_analysis": bias_analysis,
                "recommendation": self._generate_recommendation(
                    news_classification, quality_assessment, bias_analysis, overall_score
                ),
                "url": url,
                "content_preview": content[:200] + "..." if len(content) > 200 else content,
                "analysis_timestamp": datetime.now(timezone.utc).isoformat()
            }

            logger.info(f"✅ Analysis complete. Scout Score: {overall_score:.2f}")
            return comprehensive_analysis

        except Exception as e:
            logger.error(f"❌ Comprehensive analysis failed: {e}")
            return {
                "scout_score": 0.0,
                "error": str(e),
                "url": url,
                "analysis_timestamp": datetime.now(timezone.utc).isoformat()
            }

    def batch_analyze_content(self, content_list: list[tuple[str, str]]) -> list[dict]:
        """
        Batch process multiple content items for efficiency
        """
        logger.info(f"🔄 Starting batch analysis of {len(content_list)} items")

        results = []
        batch_size = 4  # Optimized for 8GB memory allocation

        for i in range(0, len(content_list), batch_size):
            batch = content_list[i:i + batch_size]

            for content, url in batch:
                try:
                    analysis = self.comprehensive_content_analysis(content, url)
                    results.append(analysis)
                except Exception as e:
                    logger.error(f"❌ Batch analysis failed for {url}: {e}")
                    results.append({
                        "scout_score": 0.0,
                        "error": str(e),
                        "url": url,
                        "analysis_timestamp": datetime.now(timezone.utc).isoformat()
                    })

        logger.info(f"✅ Batch analysis complete. {len(results)} items processed")
        return results

    def _extract_json_response(self, text: str) -> dict:
        """Extract JSON from model response with robust fallback parsing"""
        try:
            # Clean the text first
            text = text.strip()

            # Method 1: Try to find complete JSON block
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

            # Method 2: Try to extract key-value pairs and construct JSON
            result = {}

            # Look for common patterns
            patterns = {
                'is_news': r'"?is_news"?\s*:?\s*([tT]rue|[fF]alse|true|false)',
                'confidence': r'"?confidence"?\s*:?\s*([0-9]*\.?[0-9]+)',
                'content_type': r'"?content_type"?\s*:?\s*"?([^"]+)"?',
                'reasoning': r'"?reasoning"?\s*:?\s*"?([^"]+)"?',
                'overall_quality': r'"?overall_quality"?\s*:?\s*([0-9]*\.?[0-9]+)',
                'bias_score': r'"?bias_score"?\s*:?\s*([0-9]*\.?[0-9]+)'
            }

            for key, pattern in patterns.items():
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip('"')
                    if key == 'is_news':
                        result[key] = value.lower() in ['true', '1', 'yes']
                    elif key in ['confidence', 'overall_quality', 'bias_score']:
                        try:
                            result[key] = float(value)
                        except ValueError:
                            result[key] = 0.0
                    else:
                        result[key] = value

            # Set defaults if not found
            if 'is_news' not in result:
                result['is_news'] = 'news' in text.lower()
            if 'confidence' not in result:
                result['confidence'] = 0.5
            if 'content_type' not in result:
                result['content_type'] = 'news' if result.get('is_news', False) else 'other'
            if 'reasoning' not in result:
                result['reasoning'] = 'Extracted from AI response'

            return result

        except Exception as e:
            logger.error(f"JSON parsing error: {e}")
            # Final fallback - analyze text heuristically
            return {
                "is_news": any(keyword in text.lower() for keyword in ['news', 'article', 'report', 'breaking']),
                "confidence": 0.3,
                "content_type": "unknown",
                "reasoning": f"Fallback parsing due to error: {str(e)}",
                "raw_response": text[:200]  # Truncate for logging
            }

    def _calculate_scout_score(self, news_class: dict, quality: dict, bias: dict) -> float:
        """Calculate overall Scout score for content filtering"""
        try:
            # Base news confidence
            news_score = news_class.get("confidence", 0.0) if news_class.get("is_news", False) else 0.0

            # Quality weighted score
            quality_score = quality.get("overall_quality", 0.0)

            # Bias penalty (high bias reduces score)
            bias_penalty = 1.0 - bias.get("bias_score", 0.5)

            # Combined Scout score
            scout_score = (news_score * 0.4 + quality_score * 0.4 + bias_penalty * 0.2)

            return min(max(scout_score, 0.0), 1.0)  # Clamp to [0, 1]

        except Exception as e:
            logger.error(f"Scout score calculation error: {e}")
            return 0.0

    def _generate_recommendation(self, news_class: dict, quality: dict, bias: dict, scout_score: float) -> str:
        """Generate recommendation for downstream processing"""
        if scout_score >= 0.8:
            return "HIGH_PRIORITY: Excellent news content for immediate processing"
        elif scout_score >= 0.6:
            return "MEDIUM_PRIORITY: Good quality news content"
        elif scout_score >= 0.4:
            return "LOW_PRIORITY: Borderline content, manual review recommended"
        else:
            return "REJECT: Poor quality or non-news content, exclude from pipeline"

    def cleanup(self):
        """Clean up GPU memory"""
        if self.device == "cuda":
            torch.cuda.empty_cache()
            logger.info("🧹 GPU memory cleaned up")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
