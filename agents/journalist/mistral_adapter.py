"""LLM helper for the Journalist agent backed by the shared Mistral adapter."""
from __future__ import annotations

from typing import Any, Dict

from agents.common.base_mistral_json_adapter import BaseMistralJSONAdapter

SYSTEM_PROMPT = (
    "You are the JustNews field journalist assistant. Given freshly crawled "
    "content, produce a concise JSON brief with keys: headline, summary, "
    "key_points (list of bullet strings), leads (list), follow_up_questions "
    "(list), and risk_flags (list). Keep the tone factual and actionable."
)


class JournalistMistralAdapter(BaseMistralJSONAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_name="journalist",
            adapter_name="mistral_journalist_v1",
            system_prompt=SYSTEM_PROMPT,
            disable_env="JOURNALIST_DISABLE_MISTRAL",
            defaults={"max_chars": 9000, "max_new_tokens": 400, "temperature": 0.25, "top_p": 0.92},
        )

    def generate_story_brief(self, markdown: str | None, html: str | None = None, *, url: str | None = None, title: str | None = None) -> Dict[str, Any] | None:
        content = markdown or html or ""
        trimmed = self._truncate_content(content)
        if not trimmed:
            return None
        title_line = f"Title: {title}\n" if title else ""
        user_block = f"{title_line}URL: {url or 'unknown'}\nContent:\n'''{trimmed}'''"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        doc = self._chat_json(messages)
        if doc and url:
            doc.setdefault("url", url)
        return doc
