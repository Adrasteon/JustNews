"""High-accuracy editorial assessor for the Chief Editor agent."""
from __future__ import annotations

from typing import Any

from agents.common.base_mistral_json_adapter import BaseMistralJSONAdapter

SYSTEM_PROMPT = (
    "You are the JustNews chief editor. Review provided copy and respond with JSON "
    "containing: priority (urgent|high|medium|low|review), stage (intake|analysis|fact_check|" \
    "synthesis|review|publish|archive), confidence (0-1), summary, risk_flags (list), "
    "next_actions (list) and notes. Be concise and actionable."
)


class ChiefEditorMistralAdapter(BaseMistralJSONAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_name="chief_editor",
            adapter_name="mistral_chief_editor_v1",
            system_prompt=SYSTEM_PROMPT,
            disable_env="CHIEF_EDITOR_DISABLE_MISTRAL",
            defaults={"max_chars": 7000, "max_new_tokens": 380, "temperature": 0.15, "top_p": 0.85},
        )

    def review_content(self, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
        text = self._truncate_content(content or "")
        if not text:
            return None
        meta = metadata or {}
        assignment = meta.get("assignment") or meta.get("topic")
        lead = f"Assignment: {assignment}\n" if assignment else ""
        user_block = f"{lead}Metadata: {meta}\nCopy:\n'''{text}'''"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        return self._chat_json(messages)
