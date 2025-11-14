"""
Journalist engine - Crawl4AI-backed discovery and AI-enhanced page reader

This engine is intentionally lightweight and delegates crawling to a local
Crawl4AI server (systemd managed) via a bridge. It exposes a small async API
that mirrors scout responsibilities but centralizes heavy LLM & browser work
in a separate process.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional
import os

from agents.c4ai.bridge import crawl_via_local_server


@dataclass
class JournalistConfig:
    """Configuration for JournalistEngine with env-driven defaults.

    Environment variables consulted:
    - CRAWL4AI_HOST (default 127.0.0.1)
    - CRAWL4AI_PORT (default 3308)
    - CRAWL4AI_USE_LLM (optional, 'true'/'false')
    """

    crawl4ai_base_url: str = (
        os.getenv("CRAWL4AI_BASE_URL")
        or f"http://{os.getenv('CRAWL4AI_HOST', '127.0.0.1')}:{os.getenv('CRAWL4AI_PORT', '3308')}"
    )
    default_mode: str = "standard"
    use_llm_extraction: bool = os.getenv("CRAWL4AI_USE_LLM", "true").lower() in ("1", "true", "yes")


class JournalistEngine:
    def __init__(self, config: JournalistConfig | None = None):
        self.config = config or JournalistConfig()
        self._shutdown = False

    async def crawl_and_analyze(self, url: str, mode: Optional[str] = None) -> Dict[str, Any]:
        mode = mode or self.config.default_mode
        # Use the bridge helper to call the local Crawl4AI server
        results = await crawl_via_local_server(url, mode=mode, use_llm=self.config.use_llm_extraction)
        # Minimal mapping / normalization - bridge returns a simple dict
        return results

    async def shutdown(self) -> None:
        self._shutdown = True
        # Perform any graceful cleanup here (if needed)
        await asyncio.sleep(0)
