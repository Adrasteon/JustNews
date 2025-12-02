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

    def batch_infer(self, prompts: List[str], **kwargs: Any) -> List[dict]:
        return [self.infer(p, **kwargs) for p in prompts]

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
