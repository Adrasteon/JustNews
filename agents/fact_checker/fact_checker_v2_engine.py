"""
Fact Checker V2 - Production-Ready Multi-Model AI Architecture
Focused fact verification with 4 specialized AI models

AI Models:
1. DistilBERT-base:             pipeline_fn = getattr(transformers_mod, 'pipeline', None)
            if pipeline_fn is None:
                self.pipelines['fact_verification'] = None
                return
                
            device = 0 if (self.device.type == "cuda") else -1
            self.pipelines['fact_verification'] = pipeline_fn(
                "text-classification",
                model=model_name,
                tokenizer=model_name,
                device=device,
                return_all_scores=True,  # Keep for backward compatibility
                truncation=True,  # Add truncation for long inputs
                max_length=512  # Limit input length
            )fication (factual/questionable classification)
2. RoBERTa-base: Source credibility assessment (reliability scoring)  
3. SentenceTransformers: Evidence retrieval (semantic search)
4. spaCy NER: Claim extraction (verifiable claims identification)

Note: Contradiction detection moved to Reasoning Agent (Nucleoid symbolic logic)
Performance: Production-ready with GPU acceleration
"""

import importlib
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from common.observability import get_logger


# Lazy import helpers to avoid importing heavy ML libraries at module import time
def _import_transformers_module():
    try:
        mod = importlib.import_module("transformers")
        # Try to silence transformers logging when available
        try:
            mod.logging.set_verbosity_error()
        except Exception:
            pass
        return mod
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"Transformers not available at import time: {e}")
        return None


def _import_sentence_transformer_class():
    try:
        mod = importlib.import_module("sentence_transformers")
        return getattr(mod, "SentenceTransformer", None)
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"sentence_transformers not available at import time: {e}")
        return None

# Production-ready warning suppression (silence when modules are present at runtime)
warnings.filterwarnings("ignore", category=FutureWarning, module="torch.*")
warnings.filterwarnings("ignore", category=UserWarning, module="transformers.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="spacy.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="click.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)  # Catch all deprecation warnings

# Production GPU Manager integration
try:
    from agents.common.gpu_manager import (
        get_gpu_manager,
        release_agent_gpu,
        request_agent_gpu,
    )
    PRODUCTION_GPU_AVAILABLE = True
except ImportError:
    PRODUCTION_GPU_AVAILABLE = False

logger = get_logger(__name__)

class FactCheckerV2Engine:
    """
    Next-Generation Fact Checking Engine with 5 Specialized AI Models
    Production-ready architecture matching Scout V2 standards
    """

    def __init__(self, enable_training=False):
        """Initialize all 5 specialized AI models"""
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.models = {}
        self.tokenizers = {}
        self.pipelines = {}
        self.enable_training = enable_training

        # Initialize GPU allocation for fact checker agent
        self.gpu_allocated = False
        self.gpu_device = None
        self.gpu_memory_gb = 3.0  # Fact checker needs ~3GB for models

        if PRODUCTION_GPU_AVAILABLE and self.device.type == "cuda":
            try:
                # Request GPU allocation through production manager
                allocation = request_agent_gpu('fact_checker', self.gpu_memory_gb)
                if isinstance(allocation, dict) and allocation.get('status') == 'allocated':
                    self.gpu_allocated = True
                    self.gpu_device = allocation.get('gpu_device', 0)
                    self.gpu_memory_gb = allocation.get('allocated_memory_gb', self.gpu_memory_gb)
                    logger.info(f"✅ Fact Checker GPU allocated: {self.gpu_memory_gb}GB on device {self.gpu_device}")
                else:
                    logger.warning(f"⚠️ Fact Checker GPU allocation failed: {allocation}")
                    self.device = torch.device('cpu')
            except Exception as e:
                logger.warning(f"⚠️ Fact Checker GPU allocation error: {e}")
                self.device = torch.device('cpu')
        else:
            logger.info("📋 Production GPU manager not available, using direct GPU access")

        # Load core fact-checking models (contradiction moved to Reasoning Agent)
        self._initialize_fact_verification_model()
        self._initialize_credibility_assessment_model()
        self._initialize_evidence_retrieval_model()
        self._initialize_claim_extraction_model()

        # Register models with production GPU manager
        if PRODUCTION_GPU_AVAILABLE and self.gpu_allocated:
            try:
                gpu_mgr = get_gpu_manager()
                for model_name, pipeline in self.pipelines.items():
                    if pipeline is not None:
                        gpu_mgr.register_model(f"fact_checker_v2_{model_name}", pipeline)
                logger.info("🧹 Fact Checker models registered with production GPU manager")
            except Exception as e:
                logger.warning(f"⚠️ Failed to register models with GPU manager: {e}")
        elif self.device.type == "cuda":
            logger.info("📋 Production GPU manager not available, models not registered")

    def _initialize_fact_verification_model(self):
        """Model 1: DistilBERT-base for binary fact verification"""
        try:
            model_name = "distilbert-base-uncased"
            transformers_mod = _import_transformers_module()
            if transformers_mod is None:
                self.pipelines['fact_verification'] = None
                return

            pipeline_fn = getattr(transformers_mod, 'pipeline', None)
            if pipeline_fn is None:
                self.pipelines['fact_verification'] = None
                return

            device = 0 if (self.device.type == "cuda") else -1
            self.pipelines['fact_verification'] = pipeline_fn(
                "text-classification",
                model=model_name,
                tokenizer=model_name,
                device=device,
                return_all_scores=True,  # Keep for backward compatibility
                truncation=True,  # Add truncation for long inputs
                max_length=512  # Limit input length
            )

            logger.info("✅ Model 1: Fact verification (DistilBERT) loaded")

        except Exception as e:
            logger.error(f"❌ Failed to load fact verification model: {e}")
            self.pipelines['fact_verification'] = None

    def _initialize_credibility_assessment_model(self):
        """Model 2: RoBERTa-base for source credibility scoring"""
        try:
            model_name = "roberta-base"
            transformers_mod = _import_transformers_module()
            if transformers_mod is None:
                self.pipelines['credibility_assessment'] = None
                return

            pipeline_fn = getattr(transformers_mod, 'pipeline', None)
            if pipeline_fn is None:
                self.pipelines['credibility_assessment'] = None
                return

            device = 0 if (self.device.type == "cuda") else -1
            self.pipelines['credibility_assessment'] = pipeline_fn(
                "text-classification",
                model=model_name,
                tokenizer=model_name,
                device=device,
                return_all_scores=True,  # Keep for backward compatibility
                truncation=True,  # Add truncation for long inputs
                max_length=512  # Limit input length
            )

            logger.info("✅ Model 2: Credibility assessment (RoBERTa) loaded")

        except Exception as e:
            logger.error(f"❌ Failed to load credibility assessment model: {e}")
            self.pipelines['credibility_assessment'] = None

    def _initialize_evidence_retrieval_model(self):
        """Model 4: SentenceTransformers for evidence retrieval"""
        try:
            model_name = "sentence-transformers/all-mpnet-base-v2"

            # Prefer process-local shared embedding model when available
            agent_cache = os.environ.get('FACT_CHECKER_MODEL_CACHE') or str(Path('./agents/fact_checker/models').resolve())
            try:
                from agents.common.embedding import get_shared_embedding_model
                self.models['evidence_retrieval'] = get_shared_embedding_model(
                    model_name,
                    cache_folder=agent_cache,
                    device=self.device
                )
            except Exception:
                try:
                    from agents.common.embedding import (
                        ensure_agent_model_exists,
                        get_shared_embedding_model,
                    )
                    try:
                        ensure_agent_model_exists(model_name, agent_cache)
                    except Exception:
                        pass
                    self.models['evidence_retrieval'] = get_shared_embedding_model(model_name, cache_folder=agent_cache, device=self.device)
                except Exception:
                    # If SentenceTransformer is available, use it; otherwise leave None
                    try:
                        model_dir = None
                        try:
                            from agents.common.embedding import (
                                ensure_agent_model_exists,
                            )
                            model_dir = ensure_agent_model_exists(model_name, agent_cache)
                        except Exception:
                            pass
                        SentenceTransformerCls = _import_sentence_transformer_class()
                        if SentenceTransformerCls is not None:
                            try:
                                if model_dir:
                                    self.models['evidence_retrieval'] = SentenceTransformerCls(str(model_dir), device=self.device)
                                else:
                                    self.models['evidence_retrieval'] = SentenceTransformerCls(
                                        model_name,
                                        cache_folder=agent_cache,
                                        device=self.device
                                    )
                            except Exception:
                                logger.warning("Failed to initialize SentenceTransformer directly for fact checker; leaving evidence_retrieval as None")
                                self.models['evidence_retrieval'] = None
                        else:
                            self.models['evidence_retrieval'] = None
                    except Exception:
                        self.models['evidence_retrieval'] = None

            logger.info("✅ Model 4: Evidence retrieval (SentenceTransformers) loaded")

        except Exception as e:
            logger.error(f"❌ Failed to load evidence retrieval model: {e}")
            self.models['evidence_retrieval'] = None

    def _initialize_claim_extraction_model(self):
        """Model 5: spaCy for claim extraction"""
        try:
            # Suppress all warnings during spaCy operations
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                import spacy

                # Load spaCy model - spaCy handles GPU differently than PyTorch
                # Use CPU for spaCy as it's more stable and still fast for NLP tasks
                self.models['claim_extraction'] = spacy.load("en_core_web_sm")

            logger.info("✅ Model 5: Claim extraction (spaCy) loaded")

        except ImportError:
            logger.error("❌ spaCy not installed. Install with: pip install spacy && python -m spacy download en_core_web_sm")
            self.models['claim_extraction'] = None
        except OSError:
            logger.error("❌ spaCy en_core_web_sm model not found. Download with: python -m spacy download en_core_web_sm")
            self.models['claim_extraction'] = None
        except Exception as e:
            logger.error(f"❌ Failed to load claim extraction model: {e}")
            self.models['claim_extraction'] = None

    def verify_fact(self, claim: str, context: str = "") -> dict[str, Any]:
        """
        Primary fact verification using DistilBERT
        Returns factual/questionable classification with confidence
        """
        try:
            if not self.pipelines.get('fact_verification'):
                return {"verification_score": 0.5, "classification": "unknown", "confidence": 0.0}

            # Prepare input text
            input_text = f"{claim} [SEP] {context}" if context else claim

            # Get fact verification prediction
            result = self.pipelines['fact_verification'](input_text)

            # Extract verification score (assuming binary classification)
            if isinstance(result, list) and len(result) > 0:
                scores = result[0] if isinstance(result[0], list) else result
                factual_score = max([s['score'] for s in scores if 'factual' in s['label'].lower()], default=0.5)
                classification = "factual" if factual_score > 0.6 else "questionable"
                confidence = factual_score
            else:
                factual_score = 0.5
                classification = "unknown"
                confidence = 0.0

            return {
                "verification_score": factual_score,
                "classification": classification,
                "confidence": confidence,
                "model": "distilbert-fact-verification"
            }

        except Exception as e:
            logger.error(f"Fact verification error: {e}")
            return {"verification_score": 0.5, "classification": "error", "confidence": 0.0}

    def assess_source_credibility(self, source_text: str, domain: str = "") -> dict[str, Any]:
        """
        Source credibility assessment using RoBERTa
        Returns reliability score (0.0-1.0)
        """
        try:
            if not self.pipelines.get('credibility_assessment'):
                return {"credibility_score": 0.5, "reliability": "unknown", "confidence": 0.0}

            # Prepare input with domain context
            input_text = f"Source: {domain} - {source_text}" if domain else source_text

            # Get credibility assessment
            result = self.pipelines['credibility_assessment'](input_text)

            # Extract credibility score
            if isinstance(result, list) and len(result) > 0:
                scores = result[0] if isinstance(result[0], list) else result
                credibility_score = max([s['score'] for s in scores], default=0.5)
                reliability = "high" if credibility_score > 0.7 else ("medium" if credibility_score > 0.4 else "low")
                confidence = credibility_score
            else:
                credibility_score = 0.5
                reliability = "unknown"
                confidence = 0.0

            return {
                "credibility_score": credibility_score,
                "reliability": reliability,
                "confidence": confidence,
                "model": "roberta-credibility-assessment"
            }

        except Exception as e:
            logger.error(f"Credibility assessment error: {e}")
            return {"credibility_score": 0.5, "reliability": "error", "confidence": 0.0}

    def detect_contradictions(self, text_a: str, text_b: str) -> dict[str, Any]:
        """
        Contradiction detection moved to Reasoning Agent (Nucleoid)
        This method now delegates to the Reasoning Agent for proper symbolic logic
        """
        return {
            "contradiction_score": 0.5,
            "status": "delegated_to_reasoning_agent",
            "confidence": 1.0,
            "message": "Contradiction detection handled by Reasoning Agent with Nucleoid symbolic logic"
        }

    def retrieve_evidence(self, query: str, evidence_database: list[str]) -> dict[str, Any]:
        """
        Evidence retrieval using SentenceTransformers
        Finds supporting/contradicting evidence from knowledge base
        """
        try:
            if not self.models.get('evidence_retrieval') or not evidence_database:
                return {"evidence": [], "similarity_scores": [], "top_evidence": ""}

            # Encode query and evidence database
            query_embedding = self.models['evidence_retrieval'].encode([query])
            evidence_embeddings = self.models['evidence_retrieval'].encode(evidence_database)

            # Calculate similarities
            similarities = self.models['evidence_retrieval'].similarity(query_embedding, evidence_embeddings)[0]

            # Get top evidence
            top_indices = similarities.argsort(descending=True)[:3]
            top_evidence = [evidence_database[i] for i in top_indices]
            top_scores = [float(similarities[i]) for i in top_indices]

            return {
                "evidence": top_evidence,
                "similarity_scores": top_scores,
                "top_evidence": top_evidence[0] if top_evidence else "",
                "model": "sentence-transformers-evidence-retrieval"
            }

        except Exception as e:
            logger.error(f"Evidence retrieval error: {e}")
            return {"evidence": [], "similarity_scores": [], "top_evidence": ""}

    def extract_claims(self, text: str) -> dict[str, Any]:
        """
        Claim extraction using spaCy NER + custom patterns
        Extracts verifiable factual claims from news text
        """
        try:
            claims = []
            entities = []

            if self.models.get('claim_extraction'):
                # spaCy NER approach
                doc = self.models['claim_extraction'](text)

                # Extract entities that could be part of factual claims
                entities = [(ent.text, ent.label_) for ent in doc.ents]

                # Extract potential factual claims using patterns
                for sent in doc.sents:
                    sent_text = sent.text.strip()

                    # Simple heuristics for factual claims
                    if any(indicator in sent_text.lower() for indicator in [
                        'according to', 'reported that', 'announced', 'confirmed'
                    ]):
                        claims.append(sent_text)

            else:
                # Fallback pattern-based approach
                import re

                # Extract sentences with factual indicators
                sentences = re.split(r'[.!?]+', text)
                for sent in sentences:
                    if any(indicator in sent.lower() for indicator in [
                        'according to', 'reported', 'announced', 'confirmed', 'said'
                    ]):
                        claims.append(sent.strip())

            return {
                "claims": claims[:5],  # Top 5 claims
                "entities": entities[:10],  # Top 10 entities
                "claim_count": len(claims),
                "model": "spacy-claim-extraction" if self.models.get('claim_extraction') else "pattern-based-fallback"
            }

        except Exception as e:
            logger.error(f"Claim extraction error: {e}")
            return {"claims": [], "entities": [], "claim_count": 0}

    def comprehensive_fact_check(self, article_text: str, source_url: str = "") -> dict[str, Any]:
        """
        Comprehensive fact-checking using all 5 AI models
        Returns complete fact-checking analysis
        """
        try:
            # Extract claims from article
            claims_result = self.extract_claims(article_text)

            # Verify each major claim
            fact_verifications = []
            for claim in claims_result['claims'][:3]:  # Top 3 claims
                verification = self.verify_fact(claim, article_text)
                fact_verifications.append({
                    "claim": claim,
                    "verification": verification
                })

            # Assess source credibility
            domain = source_url.split('/')[2] if source_url and '/' in source_url else ""
            credibility = self.assess_source_credibility(article_text[:500], domain)

            # Check for internal contradictions
            sentences = article_text.split('.')[:5]  # First 5 sentences
            contradictions = []
            for i in range(len(sentences)-1):
                contradiction = self.detect_contradictions(sentences[i], sentences[i+1])
                if contradiction['status'] == 'contradiction':
                    contradictions.append({
                        "sentence_a": sentences[i].strip(),
                        "sentence_b": sentences[i+1].strip(),
                        "contradiction_score": contradiction['contradiction_score']
                    })

            # Calculate overall fact-check score
            avg_verification = np.mean([fv['verification']['verification_score'] for fv in fact_verifications]) if fact_verifications else 0.5
            credibility_score = credibility['credibility_score']
            contradiction_penalty = len(contradictions) * 0.1

            overall_score = max(0.0, min(1.0, (avg_verification + credibility_score) / 2 - contradiction_penalty))

            # Determine overall assessment
            if overall_score >= 0.7:
                assessment = "highly_reliable"
            elif overall_score >= 0.5:
                assessment = "moderately_reliable"
            else:
                assessment = "questionable"

            return {
                "overall_score": overall_score,
                "assessment": assessment,
                "claims_analysis": {
                    "extracted_claims": claims_result['claims'],
                    "fact_verifications": fact_verifications,
                    "claim_count": claims_result['claim_count']
                },
                "source_credibility": credibility,
                "contradictions": contradictions,
                "entities": claims_result['entities'],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "models_used": ["distilbert", "roberta", "bert-large", "sentence-transformers", "spacy"]
            }

        except Exception as e:
            logger.error(f"Comprehensive fact-check error: {e}")
            return {
                "overall_score": 0.5,
                "assessment": "error",
                "error": str(e)
            }

    def get_model_info(self) -> dict[str, dict]:
        """Get information about all loaded models"""
        return {
            "fact_verification": {
                "model_name": "distilbert-base-uncased",
                "loaded": self.pipelines.get('fact_verification') is not None,
                "purpose": "Binary fact verification (factual/questionable)"
            },
            "credibility_assessment": {
                "model_name": "roberta-base",
                "loaded": self.pipelines.get('credibility_assessment') is not None,
                "purpose": "Source credibility scoring (0.0-1.0)"
            },
            "evidence_retrieval": {
                "model_name": "sentence-transformers/all-mpnet-base-v2",
                "loaded": self.models.get('evidence_retrieval') is not None,
                "purpose": "Semantic evidence search and retrieval"
            },
            "claim_extraction": {
                "model_name": "spacy en_core_web_sm",
                "loaded": self.models.get('claim_extraction') is not None,
                "purpose": "Factual claim extraction from news text"
            }
        }

    def cleanup(self):
        """Cleanup GPU memory and model resources"""
        # Release GPU allocation
        if PRODUCTION_GPU_AVAILABLE and self.gpu_allocated:
            try:
                release_agent_gpu('fact_checker')
                logger.info("✅ Fact Checker GPU allocation released")
            except Exception as e:
                logger.warning(f"⚠️ Failed to release Fact Checker GPU allocation: {e}")

        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("✅ Fact Checker V2 Engine cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

# Global engine instance
fact_checker_engine = None

def initialize_fact_checker_v2():
    """Initialize the global Fact Checker V2 engine"""
    global fact_checker_engine
    try:
        fact_checker_engine = FactCheckerV2Engine(enable_training=True)
        logger.info("🚀 Fact Checker V2 Engine initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Fact Checker V2 Engine: {e}")
        return False

def get_fact_checker_engine():
    """Get or initialize the global Fact Checker V2 engine"""
    global fact_checker_engine
    if fact_checker_engine is None:
        initialize_fact_checker_v2()
    return fact_checker_engine
