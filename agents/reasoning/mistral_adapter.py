"""LLM-backed chain-of-thought helper for the Reasoning agent."""
from __future__ import annotations

from typing import Any, Dict, List

from agents.common.base_mistral_json_adapter import BaseMistralJSONAdapter

SYSTEM_PROMPT = (
    "You are the JustNews reasoning specialist. Given domain facts and a query, "
    "produce structured JSON with keys: hypothesis, chain_of_thought (list of steps), "
    "verdict (supported|refuted|unclear), confidence (0-1), follow_up_questions (list)."
)


class ReasoningMistralAdapter(BaseMistralJSONAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_name="reasoning",
            adapter_name="mistral_reasoning_v1",
            system_prompt=SYSTEM_PROMPT,
            disable_env="REASONING_DISABLE_MISTRAL",
            defaults={"max_chars": 8000, "max_new_tokens": 420, "temperature": 0.2, "top_p": 0.9},
        )

    def analyze(self, query: str, context_facts: List[str] | None = None) -> Dict[str, Any] | None:
        facts_block = "\n".join(context_facts or [])
        user_block = f"Question: {query}\nFacts:\n{facts_block or 'None provided'}"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        return self._chat_json(messages)
