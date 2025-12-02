from __future__ import annotations

import time
import os
from typing import Any, Dict, List

from .adapter_base import BaseAdapter, AdapterError
from .base_mistral_json_adapter import BaseMistralJSONAdapter
from .mistral_loader import load_mistral_adapter_or_base


class MistralAdapter(BaseAdapter):
    """Adapter wrapper exposing a small sync API over the BaseMistralJSONAdapter.

    Supports dry-run/modelstore modes by returning simulated outputs when the
    underlying loader is in dry-run mode (to avoid loading heavy weights in tests).
    """

    def __init__(self, *, agent: str, adapter_name: str, system_prompt: str = "", disable_env: str = "") -> None:
        self.agent = agent
        self.adapter_name = adapter_name
        self.system_prompt = system_prompt or ""
        self.disable_env = disable_env or f"{agent.upper()}_DISABLE_MISTRAL"
        self._base: BaseMistralJSONAdapter | None = None
        self._agent_impl: object | None = None
        self._dry_run = os.environ.get("MODEL_STORE_DRY_RUN") == "1" or os.environ.get("DRY_RUN") == "1"

    def load(self, model_id: str | None = None, config: dict | None = None) -> None:
        # Build internal base helper using existing shared class
        if self._base is None:
            self._base = BaseMistralJSONAdapter(
                agent_name=self.agent,
                adapter_name=self.adapter_name,
                system_prompt=self.system_prompt,
                disable_env=self.disable_env,
            )

        # _ensure_loaded performs loading via mistral_loader which respects dry-run
        ok = self._base._ensure_loaded()
        if not ok:
            # loader left an error (or not enabled)
            if getattr(self._base, "_load_error", None):
                raise AdapterError(f"mistral-load-error: {self._base._load_error}")
            raise AdapterError("mistral-adapter-not-available")

        # Try to lazy-load any per-agent adapter implementation so we can
        # delegate specialized helpers (classify, review, evaluate_claim,
        # generate_story_brief) without duplicating normalization code.
        try:
            module_name = f"agents.{self.agent}.mistral_adapter"
            mod = __import__(module_name, fromlist=['*'])
            # Derive class name from agent, e.g. "fact_checker" -> "FactCheckerMistralAdapter"
            parts = [p.capitalize() for p in self.agent.split('_')]
            class_name = ''.join(parts) + 'MistralAdapter'
            cls = getattr(mod, class_name, None)
            if cls:
                try:
                    self._agent_impl = cls()
                except Exception:
                    # If instantiation fails, silently ignore — we'll fall back
                    # to the base JSON adapter behavior.
                    self._agent_impl = None
        except Exception:
            # No specialized per-agent adapter available — that's fine.
            self._agent_impl = None

    def infer(self, prompt: str, **kwargs: Any) -> dict:
        if self._base is None:
            raise AdapterError("adapter-not-loaded")

        # If we are in dry-run or the loaded handles are not actual model/tokenizer objects
        if self._dry_run or isinstance(self._base.model, dict) and self._base.model.get("dry_run"):
            # simulate an output
            start = time.time()
            text = f"[DRYRUN-{self.agent}:{self.adapter_name}] Simulated reply to: {prompt[:120]}"
            return {"text": text, "raw": {"simulated": True}, "tokens": len(prompt.split()), "latency": time.time() - start}

        # Real run path
        completion = self._base._chat([{"role": "system", "content": self.system_prompt}, {"role": "user", "content": prompt}])
        if completion is None:
            raise AdapterError("mistral-infer-failed")
        return {"text": completion, "raw": completion, "tokens": len(completion.split()), "latency": 0.0}

    def summarize_cluster(self, articles: list[str], context: str | None = None) -> dict | None:
        """Create a cluster-level synthesis JSON using the underlying BaseMistralJSONAdapter.

        Returns a dict containing at least keys like `summary` and `key_points` or None
        when unavailable. In dry-run mode returns a simulated structure.
        """
        if self._base is None:
            # lazy init path — mirror load() behaviour and allow a dry-run short-circuit
            self._base = BaseMistralJSONAdapter(
                agent_name=self.agent,
                adapter_name=self.adapter_name,
                system_prompt=self.system_prompt,
                disable_env=self.disable_env,
            )

        # Dry-run: return a small simulated JSON payload consistent with other tests
        if self._dry_run or (isinstance(self._base.model, dict) and self._base.model.get("dry_run")):
            joined = " \n---\n ".join([a[:200] for a in articles if a])
            text = f"[DRYRUN-{self.agent}:{self.adapter_name}] Simulated cluster summary for {len(articles)} articles: {joined[:240]}"
            return {
                "summary": text,
                "key_points": [f"Simulated keypoint {i+1}" for i in range(min(3, len(articles)))],
                "confidence": 0.9,
            }

        # Real path: ensure loader is loaded and delegate to _chat_json on the base adapter
        ok = self._base._ensure_loaded()
        if not ok:
            return None

        snippets = [self._base._truncate_content(a) for a in articles if a]
        if not snippets:
            return None

        joined = "\n---\n".join(snippets)
        prefix = f"Context: {context}\n" if context else ""
        user_block = f"{prefix}Articles:\n'''{joined}'''"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]

        return self._base._chat_json(messages)

    def batch_infer(self, prompts: List[str], **kwargs: Any) -> List[dict]:
        return [self.infer(p, **kwargs) for p in prompts]

    # Agent-friendly helpers ----------------------------------------------
    def classify(self, text: str) -> object | None:
        """Analyst-style classifier that returns a normalized sentiment/bias structure.

        If a per-agent implementation is available we delegate to it; otherwise
        we use the base JSON adapter / dry-run simulated payload.
        """
        # Delegate to specialized adapter if it exists
        if getattr(self, '_agent_impl', None) and hasattr(self._agent_impl, 'classify'):
            return getattr(self._agent_impl, 'classify')(text)

        if not text or not text.strip():
            return None
            return None

        if self._dry_run:
            # Return a minimal compatible object similar to Analyst.AdapterResult
            from types import SimpleNamespace
            sentiment = {
                "dominant_sentiment": "neutral",
                "confidence": 0.75,
                "intensity": "mild",
                "sentiment_scores": {"positive": 0.4, "negative": 0.3, "neutral": 0.3},
                "method": "mistral_adapter",
                "model_name": self.adapter_name,
            }
            bias = {
                "has_bias": False,
                "bias_score": 0.2,
                "bias_level": "minimal",
                "confidence": 0.7,
                "method": "mistral_adapter",
            }
            return SimpleNamespace(sentiment=sentiment, bias=bias, raw={"simulated": True})

        # Real path: format and send the messages through the base helper
        snippet = (text or '').strip()
        if not snippet:
            return None

        # If base isn't loaded, still allow the dry-run or simulated path above.
        if not self._base:
            # can't call into the base for real inference; treat as unavailable
            return None

        user_block = f"Text to evaluate:\n'''{self._base._truncate_content(snippet)}'''"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        doc = self._base._chat_json(messages)
        if not doc:
            return None

        # Return the raw payload — tests / callers expect a structure similar to per-agent's AdapterResult
        return getattr(self, '_agent_impl', None) and getattr(self._agent_impl, '_normalize', lambda p, e=None: p)(doc, 0.0) or doc

    def generate_story_brief(self, markdown: str | None, html: str | None = None, *, url: str | None = None, title: str | None = None):
        if getattr(self, '_agent_impl', None) and hasattr(self._agent_impl, 'generate_story_brief'):
            return getattr(self._agent_impl, 'generate_story_brief')(markdown, html, url=url, title=title)

        if not markdown and not html:
            return None

        if self._dry_run:
            return {"headline": f"Simulated brief for {title or url or 'content'}", "summary": "Simulated summary", "url": url}

        # Fallback to base JSON chat
        content = markdown or html or ""
        trimmed = self._base._truncate_content(content)
        if not trimmed:
            return None
        title_line = f"Title: {title}\n" if title else ""
        user_block = f"{title_line}URL: {url or 'unknown'}\nContent:\n'''{trimmed}'''"
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user_block}]
        doc = self._base._chat_json(messages)
        if doc and url:
            doc.setdefault("url", url)
        return doc

    def review(self, content: str, url: str | None = None):
        if getattr(self, '_agent_impl', None) and hasattr(self._agent_impl, 'review'):
            return getattr(self._agent_impl, 'review')(content, url)

        if not content or not content.strip():
            return None

        if self._dry_run:
            # Simulated critic assessment
            from types import SimpleNamespace
            return SimpleNamespace(
                quality=0.6,
                bias=0.3,
                consistency=0.5,
                readability=0.7,
                originality=0.6,
                overall=0.6,
                assessment="Simulated critique.",
                recommendations=["Rewrite headline", "Add sources"],
            )

        if not self._base._ensure_loaded():
            return None

        trimmed = self._base._truncate_content(content)
        url_line = f"\nSource: {url}" if url else ""
        user_block = f"Article:\n'''{trimmed}'''{url_line}"
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user_block}]
        doc = self._base._chat_json(messages)
        return getattr(self, '_agent_impl', None) and getattr(self._agent_impl, '_normalize', lambda p: p)(doc)

    def evaluate_claim(self, claim: str, context: str | None = None):
        if getattr(self, '_agent_impl', None) and hasattr(self._agent_impl, 'evaluate_claim'):
            return getattr(self._agent_impl, 'evaluate_claim')(claim, context)

        if not claim or not claim.strip():
            return None

        if self._dry_run:
            from types import SimpleNamespace
            return SimpleNamespace(verdict="unclear", confidence=0.6, score=0.6, rationale="Simulated", evidence_needed=False)

        if not self._base._ensure_loaded():
            return None

        context_block = f"\nContext:\n{context}" if context else ""
        user_block = f"Claim:\n'''{self._base._truncate_content(claim)}'''{context_block}"
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user_block}]
        doc = self._base._chat_json(messages)
        return getattr(self, '_agent_impl', None) and getattr(self._agent_impl, '_normalize', lambda p: p)(doc)

    def health_check(self) -> dict:
        if self._base is None:
            return {"available": False, "reason": "not_loaded"}
        return {"available": self._base.is_available, "load_error": getattr(self._base, "_load_error", None)}

    def unload(self) -> None:
        if self._base is not None:
            try:
                self._base.model = None
                self._base.tokenizer = None
            except Exception:
                pass

    def metadata(self) -> dict:
        return {"agent": self.agent, "adapter": self.adapter_name, "dry_run": self._dry_run}
