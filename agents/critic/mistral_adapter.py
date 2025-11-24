"""High-accuracy editorial critique helper backed by the Critic Mistral adapter."""
from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass
from typing import Any, Dict, List

from common.observability import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - optional heavy dependency
    import torch
    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

MODEL_ADAPTER_NAME = "mistral_critic_v1"
DISABLE_ENV = "CRITIC_DISABLE_MISTRAL"
SYSTEM_PROMPT = (
    "You are the JustNews editorial chief. Review the provided article and respond\n"
    "with JSON using this schema:{\n"
    '  "quality_score": 0.0-1.0,\n'
    '  "bias_score": 0.0-1.0,\n'
    '  "consistency_score": 0.0-1.0,\n'
    '  "readability_score": 0.0-1.0,\n'
    '  "originality_score": 0.0-1.0,\n'
    '  "overall_score": 0.0-1.0,\n'
    '  "assessment": "One brief paragraph",\n'
    '  "recommendations": ["sentence", ...]\n'
    "}\n"
    "Focus on accuracy; when unsure lower the corresponding score. Output valid JSON only."
)


@dataclass(frozen=True)
class CriticAssessment:
    quality: float
    bias: float
    consistency: float
    readability: float
    originality: float
    overall: float
    assessment: str
    recommendations: List[str]


class CriticMistralAdapter:
    """Lazy loader and inference helper for editorial critiques."""

    def __init__(self) -> None:
        self.enabled = os.environ.get(DISABLE_ENV, "0").lower() not in {"1", "true", "yes", "on"}
        self.max_chars = int(os.environ.get("CRITIC_MISTRAL_MAX_CHARS", "6000"))
        self.max_input_tokens = int(os.environ.get("CRITIC_MISTRAL_MAX_INPUT_TOKENS", "2048"))
        self.max_new_tokens = int(os.environ.get("CRITIC_MISTRAL_MAX_NEW_TOKENS", "400"))
        self.temperature = float(os.environ.get("CRITIC_MISTRAL_TEMPERATURE", "0.2"))
        self.top_p = float(os.environ.get("CRITIC_MISTRAL_TOP_P", "0.8"))
        self.model = None
        self.tokenizer = None
        self._load_attempted = False
        self._load_error: str | None = None
        self._last_hash: int | None = None
        self._last_result: CriticAssessment | None = None

    def review(self, content: str, url: str | None = None) -> CriticAssessment | None:
        if not self.enabled or not content.strip():
            return None

        content_hash = hash((content, url))
        if self._last_hash == content_hash and self._last_result is not None:
            return self._last_result

        payload = self._run_inference(content, url)
        if not payload:
            return None
        result = self._normalize(payload)
        if result:
            self._last_hash = content_hash
            self._last_result = result
        return result

    # Internal helpers -------------------------------------------------

    def _ensure_loaded(self) -> bool:
        if self.model is not None and self.tokenizer is not None:
            return True
        if self._load_attempted:
            return False
        self._load_attempted = True

        if not TORCH_AVAILABLE:
            self._load_error = "torch-missing"
            logger.debug("PyTorch unavailable; cannot load Critic adapter")
            return False
        if not os.environ.get("MODEL_STORE_ROOT"):
            self._load_error = "model-store-missing"
            logger.debug("MODEL_STORE_ROOT not configured; skipping Critic adapter load")
            return False
        try:
            from agents.common.model_loader import load_transformers_with_adapter
        except Exception as exc:  # pragma: no cover
            self._load_error = str(exc)
            logger.warning("Model loader import failed for Critic adapter: %s", exc)
            return False

        try:
            model, tokenizer = load_transformers_with_adapter(
                "critic",
                adapter_name=MODEL_ADAPTER_NAME,
                model_kwargs={"device_map": "auto", "low_cpu_mem_usage": True, "trust_remote_code": True},
                tokenizer_kwargs={"use_fast": True},
            )
            model.eval()
            self.model = model
            self.tokenizer = tokenizer
            logger.info("Loaded Critic Mistral adapter (%s)", MODEL_ADAPTER_NAME)
            return True
        except Exception as exc:  # pragma: no cover
            self._load_error = str(exc)
            logger.warning("Failed to load Critic adapter: %s", exc)
            return False

    def _run_inference(self, content: str, url: str | None) -> Dict[str, Any] | None:
        if not self._ensure_loaded() or not TORCH_AVAILABLE or self.model is None or self.tokenizer is None:
            return None

        truncated = textwrap.shorten(content.strip(), width=self.max_chars, placeholder="...")
        url_line = f"\nSource: {url}" if url else ""
        prompt = self._build_prompt(truncated, url_line)

        try:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_input_tokens,
            )
        except Exception as exc:
            logger.warning("Critic tokenizer failed: %s", exc)
            return None

        device = None
        if hasattr(self.model, "device"):
            device = getattr(self.model, "device")
        elif hasattr(self.model, "hf_device_map"):
            device = None

        if device is not None and TORCH_AVAILABLE:
            inputs = {k: v.to(device) for k, v in inputs.items()}

        try:
            with torch.no_grad():
                output_ids = self.model.generate(  # type: ignore[attr-defined]
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    do_sample=False,
                    eos_token_id=self.tokenizer.eos_token_id,
                )
        except Exception as exc:
            logger.warning("Critic adapter generation failed: %s", exc)
            return None

        generated = output_ids[:, inputs["input_ids"].shape[-1]:]
        completion = self.tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        return self._parse_completion(completion)

    def _build_prompt(self, content: str, url_line: str) -> str:
        if self.tokenizer and hasattr(self.tokenizer, "apply_chat_template"):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Article:\n'''{content}'''{url_line}"},
            ]
            try:
                return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                pass
        return f"<s>[INST] {SYSTEM_PROMPT}\nArticle:\n'''{content}'''{url_line} [/INST]"

    def _parse_completion(self, completion: str) -> Dict[str, Any] | None:
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
                logger.debug("Failed to parse Critic adapter JSON: %s", snippet)
                return None

    def _normalize(self, payload: Dict[str, Any]) -> CriticAssessment | None:
        try:
            def clamp(value: float) -> float:
                return max(0.0, min(float(value), 1.0))

            quality = clamp(payload.get("quality_score", 0.6))
            bias = clamp(payload.get("bias_score", 0.4))
            consistency = clamp(payload.get("consistency_score", 0.5))
            readability = clamp(payload.get("readability_score", 0.7))
            originality = clamp(payload.get("originality_score", 0.6))
            overall = clamp(payload.get("overall_score", (quality + consistency + readability) / 3))
            assessment = str(payload.get("assessment", "Adapter could not summarize its critique."))
            recommendations = payload.get("recommendations")
            if not isinstance(recommendations, list):
                recommendations = [str(recommendations)] if recommendations else []
            recommendations = [str(item) for item in recommendations if str(item).strip()]
            return CriticAssessment(
                quality=quality,
                bias=bias,
                consistency=consistency,
                readability=readability,
                originality=originality,
                overall=overall,
                assessment=assessment,
                recommendations=recommendations,
            )
        except Exception as exc:
            logger.warning("Failed to normalize Critic adapter output: %s", exc)
            return None
