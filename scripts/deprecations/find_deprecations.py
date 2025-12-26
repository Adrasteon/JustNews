#!/usr/bin/env python3
"""Find potential deprecations by scanning for common patterns.

Usage: python scripts/deprecations/find_deprecations.py [--output baseline.json]

This is a conservative helper that finds textual occurrences of patterns we want to
monitor over time (e.g., datetime.utcnow(), asyncio.get_event_loop().run_until_complete,
and .dict()), and prints a JSON report which can be used as a baseline for QA.
"""

import json
import re
import sys
from pathlib import Path

# Patterns we track (textual) and short suggestion messages
PATTERNS = {
    r"\bdatetime\.utcnow\(": "Use timezone-aware datetimes: datetime.now(timezone.utc)",
    r"asyncio\.get_event_loop\(\)\.run_until_complete": "Use asyncio.run() or async tests",
    r"\.run_until_complete\(": "Avoid run_until_complete; prefer asyncio.run or use async tests",
    r"\.dict\(\)": "Pydantic v2: prefer model_dump() instead of dict() where appropriate",
}

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "third_party",
    ".mypy_cache",
    "__pycache__",
    "deprecations",
}


def scan(path: Path):
    results = {pat: [] for pat in PATTERNS}

    for p in path.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue

        try:
            text = p.read_text()
        except Exception:
            continue

        for pat in PATTERNS:
            for i, line in enumerate(text.splitlines(), start=1):
                if re.search(pat, line):
                    results[pat].append(
                        {"path": str(p), "line": i, "content": line.strip()}
                    )

    return results


def main(argv: list[str]):
    root = Path.cwd()
    out = None
    if len(argv) > 1 and argv[1].startswith("--output"):
        parts = argv[1].split("=", 1)
        out = parts[1] if len(parts) == 2 else "deprecations_baseline.json"

    report = scan(root)

    if out:
        Path(out).write_text(json.dumps(report, indent=2))
        print(f"Wrote baseline to {out}")
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(sys.argv)
