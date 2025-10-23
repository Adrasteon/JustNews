import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import numpy as np
import torch

from common.observability import get_logger

# Core ML Libraries
try:
    from transformers import (  # noqa: F401
        AutoConfig,
        AutoModel,
        AutoModelForSequenceClassification,
        AutoTokenizer,
        BertForSequenceClassification,
        BertModel,
        BertTokenizer,
        DistilBertForSequenceClassification,
        DistilBertModel,
        DistilBertTokenizer,
        RobertaForSequenceClassification,
        RobertaModel,
        RobertaTokenizer,
        T5ForConditionalGeneration,
        T5Tokenizer,
        pipeline,
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logging.warning("transformers not available - falling back to basic processing")

try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not available")
from pathlib import Path

try:
    from sklearn.cluster import KMeans  # noqa: F401
    from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("sklearn not available")

# Configuration
FEEDBACK_LOG = os.environ.get("CHIEF_EDITOR_V2_FEEDBACK_LOG", "./feedback_chief_editor_v2.log")
MODEL_CACHE_DIR = os.environ.get("CHIEF_EDITOR_V2_CACHE", "./models/chief_editor_v2")


logger = get_logger(__name__)

class EditorialPriority(Enum):
    """Editorial priority levels"""
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REVIEW = "review"

class WorkflowStage(Enum):
    """Editorial workflow stages"""
    INTAKE = "intake"
    ANALYSIS = "analysis"
    FACT_CHECK = "fact_check"
    SYNTHESIS = "synthesis"
    REVIEW = "review"
    PUBLISH = "publish"
    ARCHIVE = "archive"

@dataclass
class EditorialDecision:
    """Editorial decision data structure"""
    priority: EditorialPriority
    stage: WorkflowStage
    confidence: float
    reasoning: str
    next_actions: list[str]
    agent_assignments: dict[str, str]
    metadata: dict[str, Any]

@dataclass
class ChiefEditorV2Config:
    """Configuration for Chief Editor V2 Engine"""

    # Model configurations
    bert_model: str = "bert-base-uncased"
    distilbert_model: str = "distilbert-base-uncased"
    roberta_model: str = "roberta-base"
    t5_model: str = "t5-small"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Decision parameters
    quality_threshold: float = 0.7
    priority_threshold: float = 0.8
    confidence_threshold: float = 0.6

    # Performance parameters
    batch_size: int = 16
    max_length: int = 512
    device: str = "cuda" if torch.cuda.is_available() else "cpu"

    # Cache settings
    use_cache: bool = True
    cache_dir: str = MODEL_CACHE_DIR

class ChiefEditorV2Engine:
    """
    Advanced 5-Model Editorial Workflow Engine for Content Decision Making
    
    Capabilities:
    - Content quality assessment with BERT
    - Fast article categorization with DistilBERT  
    - Editorial sentiment analysis with RoBERTa
    - Commentary generation with T5
    - Workflow embeddings with SentenceTransformer
    """

    def __init__(self, config: ChiefEditorV2Config | None = None):
        self.config = config or ChiefEditorV2Config()
        self.device = torch.device(self.config.device)

        # Model containers
        self.models = {}
        self.tokenizers = {}
        self.pipelines = {}

        # Workflow state
        self.agent_capabilities = {
            "scout": ["content_discovery", "quality_assessment"],
            "analyst": ["sentiment_analysis", "bias_detection"],
            "fact_checker": ["fact_verification", "credibility_assessment"],
            "synthesizer": ["content_aggregation", "summarization"],
            "critic": ["content_review", "quality_control"]
        }

        # Initialize models
        self._initialize_models()

        logger.info(f"✅ Chief Editor V2 Engine initialized on {self.device}")

    def _initialize_models(self):
        """Initialize all 5 AI models with proper error handling"""

        try:
            # Model 1: BERT for quality assessment
            self._load_bert_model()

            # Model 2: DistilBERT for categorization
            self._load_distilbert_model()

            # Model 3: RoBERTa for sentiment analysis
            self._load_roberta_model()

            # Model 4: T5 for commentary generation
            self._load_t5_model()

            # Model 5: SentenceTransformer for workflow embeddings
            self._load_embedding_model()

        except Exception as e:
            logger.error(f"Error initializing Chief Editor V2 models: {e}")
            raise

    def _load_bert_model(self):
        """Load BERT model for content quality assessment"""
        try:
            if not TRANSFORMERS_AVAILABLE:
                logger.warning("Transformers not available - skipping BERT")
                return

            self.models['bert'] = BertForSequenceClassification.from_pretrained(
                self.config.bert_model,
                cache_dir=self.config.cache_dir,
                num_labels=5,  # Quality scores 1-5
                dtype=torch.float16 if self.device.type == 'cuda' else torch.float32
            ).to(self.device)

            self.tokenizers['bert'] = BertTokenizer.from_pretrained(
                self.config.bert_model,
                cache_dir=self.config.cache_dir
            )

            # Create quality assessment pipeline
            self.pipelines['bert_quality'] = pipeline(
                "text-classification",
                model=self.models['bert'],
                tokenizer=self.tokenizers['bert'],
                device=0 if self.device.type == 'cuda' else -1,
                return_all_scores=True
            )

            logger.info("✅ BERT quality assessment model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading BERT model: {e}")
            self.models['bert'] = None

    def _load_distilbert_model(self):
        """Load DistilBERT model for fast categorization"""
        try:
            if not TRANSFORMERS_AVAILABLE:
                logger.warning("Transformers not available - skipping DistilBERT")
                return

            self.models['distilbert'] = DistilBertForSequenceClassification.from_pretrained(
                self.config.distilbert_model,
                cache_dir=self.config.cache_dir,
                num_labels=8,  # News categories
                dtype=torch.float16 if self.device.type == 'cuda' else torch.float32
            ).to(self.device)

            self.tokenizers['distilbert'] = DistilBertTokenizer.from_pretrained(
                self.config.distilbert_model,
                cache_dir=self.config.cache_dir
            )

            # Create categorization pipeline
            self.pipelines['distilbert_category'] = pipeline(
                "text-classification",
                model=self.models['distilbert'],
                tokenizer=self.tokenizers['distilbert'],
                device=0 if self.device.type == 'cuda' else -1,
                return_all_scores=True
            )

            logger.info("✅ DistilBERT categorization model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading DistilBERT model: {e}")
            self.models['distilbert'] = None

    def _load_roberta_model(self):
        """Load RoBERTa model for editorial sentiment analysis"""
        try:
            if not TRANSFORMERS_AVAILABLE:
                logger.warning("Transformers not available - skipping RoBERTa")
                return

            # Use pre-trained sentiment model
            model_name = "cardiffnlp/twitter-roberta-base-sentiment-latest"

            self.pipelines['roberta_sentiment'] = pipeline(
                "sentiment-analysis",
                model=model_name,
                device=0 if self.device.type == 'cuda' else -1,
                return_all_scores=True
            )

            logger.info("✅ RoBERTa sentiment analysis model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading RoBERTa model: {e}")
            self.models['roberta'] = None

    def _load_t5_model(self):
        """Load T5 model for editorial commentary generation"""
        try:
            if not TRANSFORMERS_AVAILABLE:
                logger.warning("Transformers not available - skipping T5")
                return

            self.models['t5'] = T5ForConditionalGeneration.from_pretrained(
                self.config.t5_model,
                cache_dir=self.config.cache_dir,
                dtype=torch.float16 if self.device.type == 'cuda' else torch.float32
            ).to(self.device)

            self.tokenizers['t5'] = T5Tokenizer.from_pretrained(
                self.config.t5_model,
                cache_dir=self.config.cache_dir
            )

            # Create text generation pipeline
            self.pipelines['t5_commentary'] = pipeline(
                "text2text-generation",
                model=self.models['t5'],
                tokenizer=self.tokenizers['t5'],
                device=0 if self.device.type == 'cuda' else -1,
                max_length=256,
                temperature=0.7
            )

            logger.info("✅ T5 commentary generation model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading T5 model: {e}")
            self.models['t5'] = None

    def _load_embedding_model(self):
        """Load SentenceTransformer model for workflow embeddings"""
        try:
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.warning("SentenceTransformers not available - using basic routing")
                return
            # Prefer shared helper to reuse process-local model
            try:
                from agents.common.embedding import get_shared_embedding_model
                agent_cache = os.environ.get('CHIEF_EDITOR_MODEL_CACHE') or str(Path('./agents/chief_editor/models').resolve())
                self.models['embeddings'] = get_shared_embedding_model(
                    self.config.embedding_model,
                    cache_folder=agent_cache,
                    device=self.device
                )
            except Exception:
                agent_cache = os.environ.get('CHIEF_EDITOR_MODEL_CACHE') or str(Path('./agents/chief_editor/models').resolve())
                # Ensure local agent model dir if possible (best-effort)
                try:
                    from agents.common.embedding import ensure_agent_model_exists
                    try:
                        ensure_agent_model_exists(self.config.embedding_model, agent_cache)
                    except Exception:
                        pass
                except Exception:
                    pass
                # Try helper once more; if it fails, leave embeddings as None to be handled upstream
                try:
                    from agents.common.embedding import get_shared_embedding_model
                    self.models['embeddings'] = get_shared_embedding_model(self.config.embedding_model, cache_folder=agent_cache, device=self.device)
                except Exception:
                    logger.warning("ChiefEditor embedding model unavailable via helper; leaving as None")
                    self.models['embeddings'] = None

            # Move to GPU if available and supported
            try:
                if self.device.type == 'cuda' and hasattr(self.models['embeddings'], 'to'):
                    self.models['embeddings'] = self.models['embeddings'].to(self.device)
            except Exception:
                logger.debug("Unable to move chief editor embedding model to CUDA device; continuing on CPU")

            logger.info("✅ SentenceTransformer workflow embedding model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading embedding model: {e}")
            self.models['embeddings'] = None

    def log_feedback(self, event: str, details: dict[str, Any]):
        """Log feedback for editorial decision tracking"""
        try:
            with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()}\t{event}\t{details}\n")
        except Exception as e:
            logger.error(f"Error logging feedback: {e}")

    def assess_content_quality_bert(self, text: str) -> dict[str, Any]:
        """Assess content quality using BERT model"""
        try:
            if self.pipelines.get('bert_quality') is None:
                return self._fallback_quality_assessment(text)

            # Truncate text if too long
            max_length = 512
            if len(text) > max_length:
                text = text[:max_length]

            results = self.pipelines['bert_quality'](text)

            # Convert to quality score (0-1)
            if results and len(results) > 0:
                # Assuming labels are quality levels
                quality_scores = {result['label']: result['score'] for result in results}
                overall_quality = sum(quality_scores.values()) / len(quality_scores)
            else:
                overall_quality = 0.5

            assessment = {
                "overall_quality": overall_quality,
                "detailed_scores": results,
                "assessment": "high" if overall_quality > 0.7 else "medium" if overall_quality > 0.4 else "low",
                "model": "bert"
            }

            self.log_feedback("assess_content_quality_bert", {
                "quality_score": overall_quality,
                "text_length": len(text)
            })

            return assessment

        except Exception as e:
            logger.error(f"Error in BERT quality assessment: {e}")
            return self._fallback_quality_assessment(text)

    def categorize_content_distilbert(self, text: str) -> dict[str, Any]:
        """Categorize content using DistilBERT model"""
        try:
            if self.pipelines.get('distilbert_category') is None:
                return self._fallback_categorization(text)

            # Truncate text if too long
            max_length = 512
            if len(text) > max_length:
                text = text[:max_length]

            results = self.pipelines['distilbert_category'](text)

            # Get top category
            if results and len(results) > 0:
                top_category = max(results, key=lambda x: x['score'])
                category_name = top_category['label']
                confidence = top_category['score']
            else:
                category_name = "general"
                confidence = 0.5

            categorization = {
                "category": category_name,
                "confidence": confidence,
                "all_categories": results,
                "model": "distilbert"
            }

            self.log_feedback("categorize_content_distilbert", {
                "category": category_name,
                "confidence": confidence,
                "text_length": len(text)
            })

            return categorization

        except Exception as e:
            logger.error(f"Error in DistilBERT categorization: {e}")
            return self._fallback_categorization(text)

    def analyze_editorial_sentiment_roberta(self, text: str) -> dict[str, Any]:
        """Analyze editorial sentiment using RoBERTa model"""
        try:
            if self.pipelines.get('roberta_sentiment') is None:
                return self._fallback_sentiment_analysis(text)

            # Truncate text if too long
            max_length = 512
            if len(text) > max_length:
                text = text[:max_length]

            results = self.pipelines['roberta_sentiment'](text)

            # Process sentiment results
            if results and len(results) > 0:
                sentiment_scores = {result['label']: result['score'] for result in results}

                # Get dominant sentiment
                dominant_sentiment = max(sentiment_scores.keys(), key=lambda k: sentiment_scores[k])
                dominant_score = sentiment_scores[dominant_sentiment]
            else:
                dominant_sentiment = "neutral"
                dominant_score = 0.5
                sentiment_scores = {}

            analysis = {
                "sentiment": dominant_sentiment.lower(),
                "confidence": dominant_score,
                "all_sentiments": sentiment_scores,
                "editorial_tone": self._determine_editorial_tone(dominant_sentiment, dominant_score),
                "model": "roberta"
            }

            self.log_feedback("analyze_editorial_sentiment_roberta", {
                "sentiment": dominant_sentiment,
                "confidence": dominant_score,
                "text_length": len(text)
            })

            return analysis

        except Exception as e:
            logger.error(f"Error in RoBERTa sentiment analysis: {e}")
            return self._fallback_sentiment_analysis(text)

    def generate_editorial_commentary_t5(self, text: str, context: str = "news article") -> str:
        """Generate editorial commentary using T5 model"""
        try:
            if self.pipelines.get('t5_commentary') is None:
                return self._fallback_commentary_generation(text, context)

            prompt = f"summarize editorial notes for {context}: {text[:300]}"

            result = self.pipelines['t5_commentary'](
                prompt,
                max_length=256,
                temperature=0.7,
                do_sample=True
            )

            commentary = result[0]['generated_text'] if result else "Editorial review required."

            # Clean up T5 artifacts
            if commentary.startswith("summarize editorial notes"):
                commentary = commentary.split(": ", 1)[-1].strip()

            self.log_feedback("generate_editorial_commentary_t5", {
                "input_length": len(text),
                "output_length": len(commentary),
                "context": context
            })

            return commentary

        except Exception as e:
            logger.error(f"Error in T5 commentary generation: {e}")
            return self._fallback_commentary_generation(text, context)

    def route_to_agent_embeddings(self, task_description: str, content: str = "") -> dict[str, Any]:
        """Route tasks to appropriate agents using semantic embeddings"""
        try:
            if self.models.get('embeddings') is None:
                return self._fallback_agent_routing(task_description)

            # Get task embedding
            task_text = f"{task_description} {content[:200]}"
            task_embedding = self.models['embeddings'].encode([task_text])

            # Get agent capability embeddings
            agent_scores = {}
            for agent, capabilities in self.agent_capabilities.items():
                capability_text = " ".join(capabilities)
                capability_embedding = self.models['embeddings'].encode([capability_text])

                # Calculate similarity
                if SKLEARN_AVAILABLE:
                    similarity = cosine_similarity(task_embedding, capability_embedding)[0][0]
                else:
                    # Simple dot product fallback
                    similarity = np.dot(task_embedding[0], capability_embedding[0])

                agent_scores[agent] = float(similarity)

            # Get best agent
            best_agent = max(agent_scores.keys(), key=lambda k: agent_scores[k])
            best_score = agent_scores[best_agent]

            routing = {
                "recommended_agent": best_agent,
                "confidence": best_score,
                "all_scores": agent_scores,
                "agent_capabilities": self.agent_capabilities[best_agent],
                "model": "embeddings"
            }

            self.log_feedback("route_to_agent_embeddings", {
                "task": task_description,
                "recommended_agent": best_agent,
                "confidence": best_score
            })

            return routing

        except Exception as e:
            logger.error(f"Error in agent routing: {e}")
            return self._fallback_agent_routing(task_description)

    def make_editorial_decision(self, content: str, metadata: dict[str, Any] = None) -> EditorialDecision:
        """
        Make comprehensive editorial decision using all 5 models
        
        Returns:
            EditorialDecision with priority, stage, and next actions
        """
        try:
            metadata = metadata or {}

            # Run all analysis models
            quality_assessment = self.assess_content_quality_bert(content)
            categorization = self.categorize_content_distilbert(content)
            sentiment_analysis = self.analyze_editorial_sentiment_roberta(content)

            # Determine priority based on all factors
            priority = self._determine_priority(
                quality_assessment, categorization, sentiment_analysis, metadata
            )

            # Determine workflow stage
            stage = self._determine_workflow_stage(
                quality_assessment, categorization, metadata
            )

            # Calculate overall confidence
            confidences = [
                quality_assessment.get('overall_quality', 0.5),
                categorization.get('confidence', 0.5),
                sentiment_analysis.get('confidence', 0.5)
            ]
            overall_confidence = sum(confidences) / len(confidences)

            # Generate reasoning
            reasoning = self.generate_editorial_commentary_t5(
                content, context=f"{categorization['category']} article"
            )

            # Determine next actions
            next_actions = self._determine_next_actions(priority, stage, quality_assessment)

            # Route to agents
            agent_routing = self.route_to_agent_embeddings(
                f"Process {categorization['category']} content for {stage.value}",
                content
            )

            decision = EditorialDecision(
                priority=priority,
                stage=stage,
                confidence=overall_confidence,
                reasoning=reasoning,
                next_actions=next_actions,
                agent_assignments={agent_routing['recommended_agent']: "primary"},
                metadata=metadata or {}
            )

            return decision
        except Exception as e:
            logger.error(f"Error making editorial decision: {e}")
            return self._fallback_editorial_decision(content, metadata)

    def _determine_workflow_stage(self, quality_assessment, categorization, metadata):
        """Determine appropriate workflow stage"""
        quality_score = quality_assessment.get('overall_quality', 0.5)

        # Check metadata for stage indicators
        if metadata.get('is_new', True):
            return WorkflowStage.INTAKE
        elif metadata.get('needs_fact_check', False):
            return WorkflowStage.FACT_CHECK
        elif quality_score < 0.5:
            return WorkflowStage.REVIEW
        else:
            return WorkflowStage.ANALYSIS

    def _determine_priority(self, quality_assessment, categorization, sentiment_analysis, metadata):
        """Determine editorial priority from multiple signals"""
        quality_score = quality_assessment.get('overall_quality', 0.5)
        category_confidence = categorization.get('confidence', 0.5)
        sentiment_confidence = sentiment_analysis.get('confidence', 0.5)

        # Calculate priority score
        priority_score = (quality_score + category_confidence + sentiment_confidence) / 3

        # Check for urgency indicators in metadata
        urgent_keywords = ['breaking', 'urgent', 'alert', 'emergency', 'crisis']
        content_lower = str((metadata or {}).get('title', '') + ' ' + (metadata or {}).get('summary', '')).lower()

        if any(keyword in content_lower for keyword in urgent_keywords):
            return EditorialPriority.URGENT
        elif priority_score > 0.8:
            return EditorialPriority.HIGH
        elif priority_score > 0.6:
            return EditorialPriority.MEDIUM
        elif priority_score > 0.4:
            return EditorialPriority.LOW
        else:
            return EditorialPriority.REVIEW

    def _determine_next_actions(self, priority, stage, quality_assessment):
        """Determine next actions based on priority and stage"""
        actions = []

        if priority == EditorialPriority.URGENT:
            actions.extend(['fast_track_review', 'assign_senior_editor'])

        if stage == WorkflowStage.INTAKE:
            actions.extend(['initial_classification', 'route_to_analyst'])
        elif stage == WorkflowStage.FACT_CHECK:
            actions.extend(['verify_facts', 'check_sources'])
        elif stage == WorkflowStage.REVIEW:
            actions.extend(['detailed_review', 'quality_improvement'])

        if quality_assessment.get('overall_quality', 0.5) < 0.4:
            actions.append('quality_enhancement_required')

        return actions

    def _determine_editorial_tone(self, sentiment, confidence):
        """Determine editorial tone from sentiment analysis"""
        if confidence < 0.6:
            return "neutral"

        sentiment_lower = sentiment.lower()
        if 'positive' in sentiment_lower or 'optimism' in sentiment_lower:
            return "positive"
        elif 'negative' in sentiment_lower or 'pessimism' in sentiment_lower:
            return "critical"
        else:
            return "balanced"

    # Fallback methods for when models are unavailable
    def _fallback_quality_assessment(self, text):
        return {
            "overall_quality": 0.5,
            "assessment": "medium",
            "model": "fallback"
        }

    def _fallback_categorization(self, text):
        return {
            "category": "general",
            "confidence": 0.5,
            "model": "fallback"
        }

    def _fallback_sentiment_analysis(self, text):
        return {
            "sentiment": "neutral",
            "confidence": 0.5,
            "editorial_tone": "balanced",
            "model": "fallback"
        }

    def _fallback_commentary_generation(self, text, context):
        return f"Editorial review required for {context}."

    def _fallback_agent_routing(self, task_description):
        return {
            "recommended_agent": "scout",
            "confidence": 0.5,
            "model": "fallback"
        }

    def _fallback_editorial_decision(self, content, metadata):
        return EditorialDecision(
            priority=EditorialPriority.MEDIUM,
            stage=WorkflowStage.REVIEW,
            confidence=0.5,
            reasoning="Fallback decision - manual review required",
            next_actions=["manual_review"],
            agent_assignments={"scout": "primary"},
            metadata=metadata or {}
        )

    def get_model_status(self) -> dict[str, bool]:
        """Get status of all models"""
        return {
            "bert": self.models.get('bert') is not None,
            "distilbert": self.models.get('distilbert') is not None,
            "roberta": self.pipelines.get('roberta_sentiment') is not None,
            "t5": self.models.get('t5') is not None,
            "embeddings": self.models.get('embeddings') is not None,
            "total_models": sum(1 for key in ['bert', 'distilbert', 'roberta', 't5', 'embeddings']
                              if self.models.get(key) is not None or
                              self.pipelines.get(f"{key}_sentiment") is not None)
        }

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

            logger.info("✅ Chief Editor V2 Engine cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

# Test the engine
def run_chief_editor_v2_engine_test():
    """Test Chief Editor V2 Engine with sample editorial decisions"""
    try:
        print("🔧 Testing Chief Editor V2 Engine...")

        config = ChiefEditorV2Config()
        engine = ChiefEditorV2Engine(config)

        # Test data
        sample_content = "Breaking news: Scientists have discovered a groundbreaking treatment for a rare disease that affects millions of people worldwide. The research team announced their findings at a major medical conference today."

        sample_metadata = {
            "title": "Medical Breakthrough Announced",
            "source": "Medical Research Institute",
            "is_new": True,
            "category_hint": "health"
        }

        # Test quality assessment
        print("🎯 Testing BERT quality assessment...")
        quality = engine.assess_content_quality_bert(sample_content)
        print(f"   Quality score: {quality['overall_quality']:.2f}")
        print(f"   Assessment: {quality['assessment']}")

        # Test categorization
        print("📂 Testing DistilBERT categorization...")
        categorization = engine.categorize_content_distilbert(sample_content)
        print(f"   Category: {categorization['category']}")
        print(f"   Confidence: {categorization['confidence']:.2f}")

        # Test sentiment analysis
        print("📊 Testing RoBERTa sentiment analysis...")
        sentiment = engine.analyze_editorial_sentiment_roberta(sample_content)
        print(f"   Sentiment: {sentiment['sentiment']}")
        print(f"   Editorial tone: {sentiment['editorial_tone']}")

        # Test commentary generation
        print("💬 Testing T5 commentary generation...")
        commentary = engine.generate_editorial_commentary_t5(sample_content)
        print(f"   Commentary length: {len(commentary)} characters")

        # Test agent routing
        print("🎯 Testing agent routing...")
        routing = engine.route_to_agent_embeddings("Analyze medical breakthrough article", sample_content)
        print(f"   Recommended agent: {routing['recommended_agent']}")
        print(f"   Confidence: {routing['confidence']:.2f}")

        # Test comprehensive editorial decision
        print("🏛️ Testing comprehensive editorial decision...")
        decision = engine.make_editorial_decision(sample_content, sample_metadata)
        print(f"   Priority: {decision.priority.value}")
        print(f"   Stage: {decision.stage.value}")
        print(f"   Confidence: {decision.confidence:.2f}")
        print(f"   Next actions: {len(decision.next_actions)}")

        # Model status
        status = engine.get_model_status()
        print(f"📋 Model status: {status['total_models']}/5 models loaded")
        print(f"   BERT: {'✅' if status['bert'] else '❌'}")
        print(f"   DistilBERT: {'✅' if status['distilbert'] else '❌'}")
        print(f"   RoBERTa: {'✅' if status['roberta'] else '❌'}")
        print(f"   T5: {'✅' if status['t5'] else '❌'}")
        print(f"   Embeddings: {'✅' if status['embeddings'] else '❌'}")

        engine.cleanup()
        print("✅ Chief Editor V2 Engine test completed successfully")

        return True

    except Exception as e:
        print(f"❌ Chief Editor V2 Engine test failed: {e}")
        return False

if __name__ == "__main__":
    run_chief_editor_v2_engine_test()
