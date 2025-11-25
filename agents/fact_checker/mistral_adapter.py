"""High-accuracy claim verification helper backed by the Fact Checker Mistral adapter."""
from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass
from typing import Any, Dict

from common.observability import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - optional heavy dep
    import torch
    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

MODEL_ADAPTER_NAME = "mistral_fact_checker_v1"
DISABLE_ENV = "FACT_CHECKER_DISABLE_MISTRAL"
SYSTEM_PROMPT = (
    "You are an expert investigative fact checker. Given a claim and optional context,\n"
    "respond with strict JSON describing whether the claim is verified, refuted, or unclear.\n"
    "Schema:{\n"
    '  "verdict": "verified|refuted|unclear",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "score": 0.0-1.0,\n'
    '  "rationale": "Single concise sentence",\n'
    '  "evidence_needed": "yes|no"\n'
    "}\n"
    "Always emit valid JSON with double quotes only."
)


@dataclass(frozen=True)
class ClaimAssessment:
    verdict: str
    confidence: float
    score: float
    rationale: str
    evidence_needed: bool


class FactCheckerMistralAdapter:
    """Lazy loader and inference helper for fact-check verification."""

    def __init__(self) -> None:
        self.enabled = os.environ.get(DISABLE_ENV, "0").lower() not in {"1", "true", "yes", "on"}
        self.max_chars = int(os.environ.get("FACT_CHECKER_MISTRAL_MAX_CHARS", "4096"))
        self.max_input_tokens = int(os.environ.get("FACT_CHECKER_MISTRAL_MAX_INPUT_TOKENS", "2048"))
        self.max_new_tokens = int(os.environ.get("FACT_CHECKER_MISTRAL_MAX_NEW_TOKENS", "320"))
        self.temperature = float(os.environ.get("FACT_CHECKER_MISTRAL_TEMPERATURE", "0.0"))
        self.top_p = float(os.environ.get("FACT_CHECKER_MISTRAL_TOP_P", "0.9"))
        self.model = None
        self.tokenizer = None
        self._load_attempted = False
        self._load_error: str | None = None

    def evaluate_claim(self, claim: str, context: str | None = None) -> ClaimAssessment | None:
        if not self.enabled or not claim.strip():
            return None
        payload = self._run_inference(claim, context)
        if not payload:
            return None
        return self._normalize(payload)

    # Internal helpers -------------------------------------------------

    def _ensure_loaded(self) -> bool:
        if self.model is not None and self.tokenizer is not None:
            return True
        if self._load_attempted:
            return False
        self._load_attempted = True

        if not TORCH_AVAILABLE:
            self._load_error = "torch-missing"
            logger.debug("PyTorch unavailable; cannot load fact-checker adapter")
            return False
        try:
            from agents.common.mistral_loader import load_mistral_adapter_or_base
        except Exception as exc:  # pragma: no cover
            self._load_error = str(exc)
            logger.warning("Shared Mistral loader import failed for fact-checker: %s", exc)
            return False

        try:
            model, tokenizer = load_mistral_adapter_or_base(
                "fact_checker",
                adapter_name=MODEL_ADAPTER_NAME,
                model_kwargs={"device_map": "auto", "low_cpu_mem_usage": True, "trust_remote_code": True},
                tokenizer_kwargs={"use_fast": True},
            )
            if model is None or tokenizer is None:
                self._load_error = "adapter-or-base-load-failed"
                logger.warning("Fact-checker adapter/base load failed despite shared loader attempt")
                return False
            model.eval()
            self.model = model
            self.tokenizer = tokenizer
            logger.info("Loaded Fact Checker Mistral weights (adapter=%s)", MODEL_ADAPTER_NAME)
            return True
        except Exception as exc:  # pragma: no cover
            self._load_error = str(exc)
            logger.warning("Failed to load Fact Checker Mistral weights: %s", exc)
            return False

    def _run_inference(self, claim: str, context: str | None) -> Dict[str, Any] | None:
        if not self._ensure_loaded() or not TORCH_AVAILABLE or self.model is None or self.tokenizer is None:
            return None

        truncated_claim = textwrap.shorten(claim.strip(), width=self.max_chars, placeholder="...")
        context_block = "\nContext:\n" + textwrap.shorten(context.strip(), width=self.max_chars, placeholder="...") if context else ""
        prompt = self._build_prompt(truncated_claim, context_block)

        try:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_input_tokens,
            )
        except Exception as exc:
            logger.warning("Fact-checker tokenizer failed: %s", exc)
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
            logger.warning("Fact-checker adapter generation failed: %s", exc)
            return None

        generated = output_ids[:, inputs["input_ids"].shape[-1]:]
        completion = self.tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        return self._parse_completion(completion)

    def _build_prompt(self, claim: str, context_block: str) -> str:
        if self.tokenizer and hasattr(self.tokenizer, "apply_chat_template"):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Claim:\n'''{claim}'''{context_block}"},
            ]
            try:
                return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                pass
        return f"<s>[INST] {SYSTEM_PROMPT}\nClaim:\n'''{claim}'''{context_block} [/INST]"

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
                logger.debug("Failed to parse fact-checker adapter JSON: %s", snippet)
                return None

    def _normalize(self, payload: Dict[str, Any]) -> ClaimAssessment | None:
        try:
            verdict = str(payload.get("verdict", "unclear")).lower()
            if verdict not in {"verified", "refuted", "unclear"}:
                verdict = "unclear"
            confidence = float(payload.get("confidence", 0.65))
            score = float(payload.get("score", 0.6 if verdict == "verified" else 0.3 if verdict == "refuted" else 0.5))
            rationale = str(payload.get("rationale", "Model could not justify the verdict."))
            evidence_needed = str(payload.get("evidence_needed", "no")).lower() in {"yes", "true"}
            return ClaimAssessment(
                verdict=verdict,
                confidence=max(0.0, min(confidence, 1.0)),
                score=max(0.0, min(score, 1.0)),
                rationale=rationale,
                evidence_needed=evidence_needed,
            )
        except Exception as exc:
            logger.warning("Failed to normalize fact-checker adapter output: %s", exc)
            return None
