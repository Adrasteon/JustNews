"""
Helper utilities for the Journalist agent.

Keep helpers small — heavy lifting is done by the crawler bridge and shared
common utilities.
"""
from __future__ import annotations

from typing import Dict


def health_check() -> Dict[str, object]:
    return {"status": "ok", "component": "journalist"}
