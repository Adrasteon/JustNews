"""Shared Mistral adapter helper for high-accuracy synthesis."""
from __future__ import annotations

from typing import Any, Dict, List

from agents.common.base_mistral_json_adapter import BaseMistralJSONAdapter

SYSTEM_PROMPT = (
    "You are the JustNews synthesis lead. Given multiple article snippets, "
    "produce JSON with summary, narrative_voice, key_points (list), cautions (list), "
    "and pull_quotes (list). Emphasize factual consistency and note any gaps."
)


class SynthesizerMistralAdapter(BaseMistralJSONAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_name="synthesizer",
            adapter_name="mistral_synth_v1",
            system_prompt=SYSTEM_PROMPT,
            disable_env="SYNTHESIZER_DISABLE_MISTRAL",
            defaults={"max_chars": 10000, "max_new_tokens": 512, "temperature": 0.3, "top_p": 0.9},
        )

    def summarize_cluster(self, articles: List[str], context: str | None = None) -> Dict[str, Any] | None:
        snippets = [self._truncate_content(a) for a in articles if a]
        if not snippets:
            return None
        joined = "\n---\n".join(snippets)
        prefix = f"Context: {context}\n" if context else ""
        user_block = f"{prefix}Articles:\n'''{joined}'''"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        return self._chat_json(messages)
