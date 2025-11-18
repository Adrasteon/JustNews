#!/usr/bin/env python3
"""
Check for suspicious processing_time patterns in code.
This script scans Python files under the repo to find places where `processing_time` is computed incorrectly,
like `time.time() - time.time()` or setting `processing_time` to `time.time()` directly.

Intended to be used as a pre-commit hook or CI step.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATTERNS = [
    # Exact no-op elapsed pattern (always zero)
    re.compile(r"time\.time\(\)\s*-\s*time\.time\(\)"),
    # Processing time assigned directly to time.time() without subtraction
    re.compile(r"[\'\"]processing_time[\'\"]\s*:\s*time\.time\(\)(?!\s*-)"),
    re.compile(r"\bprocessing_time\s*:\s*time\.time\(\)(?!\s*-)"),
]

EXCLUDES = ["/venv/", "venv/", "/.venv/", ".venv", "__pycache__", "tests/fixtures", "scripts/"]


def is_excluded(path):
    return any(ex in path for ex in EXCLUDES)


def find_issues():
    issues = []
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, ROOT)
            if is_excluded(rel):
                continue
            try:
                with open(full, encoding="utf-8") as f:
                    for n, line in enumerate(f, start=1):
                        for pattern in PATTERNS:
                            if pattern.search(line):
                                issues.append((rel, n, line.strip()))
            except Exception as e:
                print(f"Warning: could not read {full}: {e}")
    return issues


def main():
    issues = find_issues()
    if not issues:
        print("No suspicious processing_time patterns found.")
        return 0

    print("Found suspicious processing_time patterns:")
    for path, n, line in issues:
        print(f"  {path}:{n}: {line}")

    print("\nPlease fix the processing_time calculations (use start_time and compute elapsed: time.time() - start_time)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
