"""Utility helpers for producing JSON-serialisable structures.

The crawler stack frequently has to deal with third-party libraries that
return complex Python objects (for example ``lxml`` elements or datetime
instances).  Downstream services such as the memory agent expect plain JSON
payloads, so ``make_json_safe`` normalises arbitrarily nested objects into a
format that ``json.dumps`` can consume without raising errors.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

try:  # Optional dependency; ``lxml`` is not always installed.
    from lxml import etree as lxml_etree  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - dependency missing in some deployments
    lxml_etree = None  # type: ignore[assignment]


def make_json_safe(value: Any, depth: int = 0) -> Any:
    """Recursively convert ``value`` into a JSON-serialisable structure.

    The helper keeps the data layout intact (dicts remain dicts, sequences
    remain lists) but stringifies objects that JSON cannot encode.  A depth cap
    prevents runaway recursion on pathological inputs.
    """
    if depth > 32:
        return str(value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {
            str(make_json_safe(key, depth + 1)): make_json_safe(val, depth + 1)
            for key, val in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [make_json_safe(item, depth + 1) for item in value]

    if isinstance(value, set):
        return [make_json_safe(item, depth + 1) for item in value]

    if lxml_etree is not None and hasattr(value, "tag") and hasattr(value, "attrib"):
        try:
            return lxml_etree.tostring(value, encoding="unicode")
        except Exception:  # pragma: no cover - fallback makes best effort
            return str(value)

    return str(value)
