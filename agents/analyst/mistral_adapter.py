"""High-accuracy sentiment/bias scoring backed by the Analyst Mistral adapter.

This module wires the Analyst agent into the shared Mistral-7B base +
`mistral_analyst_v1` adapter published in ModelStore. It keeps the loading
lazy and optional so local development (or CI) can continue to rely on
lightweight RoBERTa/heuristic fallbacks when MODEL_STORE_ROOT or GPU/RAM are
unavailable.
"""
from __future__ import annotations

import json
import os
import re
import textwrap
import time
from dataclasses import dataclass
from typing import Any, Tuple

from common.observability import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - optional heavy dependency
    import torch
    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - keep optional
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

SYSTEM_PROMPT = (
        "You are a rigorous news analysis classifier. Evaluate the provided text\n"
        "for overall sentiment and bias. Respond with strict JSON using the schema:\n"
        "{\n"
        '  "sentiment_label": "positive|neutral|negative",\n'
        '  "sentiment_confidence": 0.0-1.0,\n'
        '  "sentiment_intensity": "mild|moderate|strong",\n'
        '  "sentiment_positive": 0.0-1.0,\n'
        '  "sentiment_negative": 0.0-1.0,\n'
        '  "bias_level": "minimal|low|medium|high",\n'
        '  "bias_score": 0.0-1.0,\n'
        '  "bias_confidence": 0.0-1.0,\n'
        '  "rationale": "One concise sentence explaining the judgment"\n'
        "}\n"
        "Keep the response compact and valid JSON only."
)

MODEL_ADAPTER_NAME = "mistral_analyst_v1"
DISABLE_ENV = "ANALYST_DISABLE_MISTRAL"


@dataclass(frozen=True)
class AdapterResult:
    sentiment: dict[str, Any]
    bias: dict[str, Any]
    raw: dict[str, Any]


class AnalystMistralAdapter:
    """Lazy loader + inference helper for the Analyst adapter."""

    def __init__(self) -> None:
        self.enabled = os.environ.get(DISABLE_ENV, "0").lower() not in {"1", "true", "yes", "on"}
        self.max_chars = int(os.environ.get("ANALYST_MISTRAL_MAX_CHARS", "6000"))
        self.max_input_tokens = int(os.environ.get("ANALYST_MISTRAL_MAX_INPUT_TOKENS", "2048"))
        self.max_new_tokens = int(os.environ.get("ANALYST_MISTRAL_MAX_NEW_TOKENS", "320"))
        self.temperature = float(os.environ.get("ANALYST_MISTRAL_TEMPERATURE", "0.15"))
        self.top_p = float(os.environ.get("ANALYST_MISTRAL_TOP_P", "0.9"))
        self.model = None
        self.tokenizer = None
        self._load_attempted = False
        self._load_error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.model is not None and self.tokenizer is not None

    def classify(self, text: str) -> AdapterResult | None:
        if not self.enabled or not text.strip():
            return None
        payload = self._run_inference(text)
        if not payload:
            return None
        parsed, elapsed = payload
        normalized = self._normalize(parsed, elapsed)
        if not normalized:
            return None
        return normalized

    # Internal helpers -------------------------------------------------

    def _ensure_loaded(self) -> bool:
        if self.is_ready:
            return True
        if self._load_attempted:
            return False
        self._load_attempted = True

        if not self.enabled:
            logger.debug("Analyst Mistral adapter disabled via %s", DISABLE_ENV)
            return False
        if not TORCH_AVAILABLE:
            logger.debug("PyTorch not available; cannot load Mistral adapter")
            self._load_error = "torch-missing"
            return False
        if not os.environ.get("MODEL_STORE_ROOT"):
            logger.debug("MODEL_STORE_ROOT not set; skipping Mistral adapter load")
            self._load_error = "model-store-missing"
            return False
        try:
            from agents.common.model_loader import load_transformers_with_adapter
        except Exception as exc:  # pragma: no cover - import guard
            self._load_error = str(exc)
            logger.warning("Model loader unavailable for Analyst adapter: %s", exc)
            return False

        try:
            model, tokenizer = load_transformers_with_adapter(
                "analyst",
                adapter_name=MODEL_ADAPTER_NAME,
                model_kwargs={"device_map": "auto", "low_cpu_mem_usage": True, "trust_remote_code": True},
                tokenizer_kwargs={"use_fast": True},
            )
            model.eval()
            self.model = model
            self.tokenizer = tokenizer
            logger.info("Loaded Analyst Mistral adapter (%s)", MODEL_ADAPTER_NAME)
            return True
        except Exception as exc:  # pragma: no cover - depends on runtime env
            self._load_error = str(exc)
            logger.warning("Failed to load Analyst Mistral adapter: %s", exc)
            return False

    def _run_inference(self, text: str) -> Tuple[dict[str, Any], float] | None:
        if not self._ensure_loaded():
            return None
        if not TORCH_AVAILABLE or self.model is None or self.tokenizer is None:
            return None

        truncated = textwrap.shorten(text.strip(), width=self.max_chars, placeholder="\n...")
        prompt = self._build_prompt(truncated)

        try:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_input_tokens,
            )
        except Exception as exc:
            logger.warning("Tokenizer failed for Analyst adapter: %s", exc)
            return None

        device = None
        if hasattr(self.model, "device"):
            device = getattr(self.model, "device")
        elif hasattr(self.model, "hf_device_map") and TORCH_AVAILABLE:
            # when accelerate shards weights; keep tensors on CPU and rely on generate()
            device = None

        if device is not None and TORCH_AVAILABLE:
            inputs = {k: v.to(device) for k, v in inputs.items()}

        try:
            with torch.no_grad():
                start = time.perf_counter()
                output_ids = self.model.generate(  # type: ignore[attr-defined]
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    do_sample=False,
                    eos_token_id=self.tokenizer.eos_token_id,
                )
                elapsed = time.perf_counter() - start
        except Exception as exc:
            logger.warning("Analyst adapter generation failed: %s", exc)
            return None

        generated = output_ids[:, inputs["input_ids"].shape[-1]:]
        completion = self.tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        payload = self._parse_completion(completion)
        if not payload:
            return None
        payload["raw_response"] = completion
        return payload, elapsed

    def _build_prompt(self, text: str) -> str:
        if self.tokenizer and hasattr(self.tokenizer, "apply_chat_template"):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Text to evaluate:\n'''{text}'''"},
            ]
            try:
                return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                pass
        return f"<s>[INST] {SYSTEM_PROMPT}\nText to evaluate:\n'''{text}''' [/INST]"

    def _parse_completion(self, completion: str) -> dict[str, Any] | None:
        snippet = completion.strip()
        fenced = re.search(r"```(?:json)?(.*?)```", snippet, flags=re.DOTALL)
        if fenced:
            snippet = fenced.group(1)
        brace = re.search(r"\{.*\}", snippet, flags=re.DOTALL)
        if brace:
            snippet = brace.group(0)
        snippet = snippet.strip()
        if not snippet:
            return None
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            try:
                sanitized = snippet.replace("'", '"')
                sanitized = re.sub(r",\s*\}", "}", sanitized)
                return json.loads(sanitized)
            except Exception:
                logger.debug("Failed to parse adapter JSON: %s", snippet)
                return None

    def _normalize(self, payload: dict[str, Any], elapsed: float) -> AdapterResult | None:
        try:
            sentiment_label = str(payload.get("sentiment_label", "neutral")).lower()
            if sentiment_label not in {"positive", "negative", "neutral"}:
                sentiment_label = "neutral"
            sentiment_conf = float(payload.get("sentiment_confidence", 0.72))
            intensity = payload.get("sentiment_intensity") or self._confidence_to_intensity(sentiment_conf)
            positive_score = float(payload.get("sentiment_positive", sentiment_conf if sentiment_label == "positive" else 1 - sentiment_conf if sentiment_label == "negative" else 0.33))
            negative_score = float(payload.get("sentiment_negative", 1.0 - positive_score))

            bias_score = float(payload.get("bias_score", 0.35))
            bias_level = payload.get("bias_level") or self._bias_level_from_score(bias_score)
            bias_conf = float(payload.get("bias_confidence", min(bias_score + 0.25, 0.95)))

            sentiment = {
                "dominant_sentiment": sentiment_label,
                "confidence": max(0.0, min(sentiment_conf, 0.99)),
                "intensity": intensity,
                "sentiment_scores": {
                    "positive": max(0.0, min(positive_score, 1.0)),
                    "negative": max(0.0, min(negative_score, 1.0)),
                    "neutral": max(0.0, min(1.0 - positive_score - negative_score, 1.0)),
                },
                "method": "mistral_adapter",
                "model_name": MODEL_ADAPTER_NAME,
                "analysis_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "reasoning": payload.get("rationale", "Adapter judgment"),
                "processing_time": elapsed,
            }

            bias = {
                "has_bias": bias_score >= 0.35,
                "bias_score": max(0.0, min(bias_score, 1.0)),
                "bias_level": bias_level,
                "confidence": max(0.0, min(bias_conf, 0.99)),
                "political_bias": float(payload.get("political_bias", bias_score * 0.6)),
                "emotional_bias": float(payload.get("emotional_bias", bias_score * 0.8)),
                "factual_bias": float(payload.get("factual_bias", max(0.0, 1.0 - bias_score))),
                "reasoning": payload.get("rationale", "Adapter judgment"),
                "method": "mistral_adapter",
                "model_used": MODEL_ADAPTER_NAME,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "processing_time": elapsed,
            }
            return AdapterResult(sentiment=sentiment, bias=bias, raw=payload)
        except Exception as exc:
            logger.warning("Failed to normalize Analyst adapter output: %s", exc)
            return None

    @staticmethod
    def _confidence_to_intensity(confidence: float) -> str:
        if confidence >= 0.8:
            return "strong"
        if confidence >= 0.6:
            return "moderate"
        return "mild"

    @staticmethod
    def _bias_level_from_score(score: float) -> str:
        if score >= 0.7:
            return "high"
        if score >= 0.45:
            return "medium"
        if score >= 0.25:
            return "low"
        return "minimal"