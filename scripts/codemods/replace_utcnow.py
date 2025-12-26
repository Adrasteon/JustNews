#!/usr/bin/env python3
"""A small codemod to find and optionally replace `datetime.utcnow()` calls
with timezone-aware `datetime.now(timezone.utc)`.

Usage:
  python scripts/codemods/replace_utcnow.py [--apply] [--root path]

This script operates conservatively:
 - by default it lists occurrences (dry-run)
 - with --apply it edits files in-place and ensures `from datetime import timezone`
   exists when necessary.

Notes:
 - This is a simple textual codemod intended for quick help; it does not attempt
   to handle every edge case (e.g., complex aliasing of imports), but it's careful
   about only replacing the `.utcnow()` suffix on tokens containing "datetime".
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT_IGNORE = {
    ".git",
    "node_modules",
    "third_party",
    "__pycache__",
    "tests/deprecation",
    "tests/codemod",
    "deprecations",
    "codemods",
}

PATTERN = re.compile(r"(?P<prefix>\b[\w\.]*datetime)\.utcnow\(\s*\)")


def find_matches(root: Path) -> list[tuple[Path, int, str]]:
    results: list[tuple[Path, int, str]] = []
    for p in root.rglob("*.py"):
        # Exclude if any identifier in ROOT_IGNORE appears in the absolute path
        if any(ignore in str(p) for ignore in ROOT_IGNORE):
            continue
        try:
            text = p.read_text()
        except Exception:
            continue

        for i, line in enumerate(text.splitlines(), start=1):
            if PATTERN.search(line):
                results.append((p, i, line.rstrip()))

    return results


def _ensure_timezone_import(text: str) -> str:
    # If timezone is already imported as 'from datetime import timezone' or
    # 'from datetime import datetime, timezone' leave as-is. Otherwise, if
    # there's a 'from datetime import' or other imports, try to append timezone
    # to the first matching 'from datetime import' line. If none found, add a
    # top-level import just after other imports.
    if "from datetime import timezone" in text:
        return text

    # Try to find `from datetime import ...` line
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("from datetime import"):
            # Insert timezone if not present
            if "timezone" not in line:
                lines[idx] = line.rstrip() + ", timezone"
            return "\n".join(lines)

    # If no specific from-import found, insert a top-level import after the
    # initial block of comments / shebang / encoding lines and before other imports
    insert_idx = 0
    for idx, line in enumerate(lines[:20]):
        if line.strip().startswith("import") or line.strip().startswith("from"):
            insert_idx = idx
            break

    # Insert at insert_idx
    lines.insert(insert_idx, "from datetime import timezone")
    return "\n".join(lines)


def apply_replacements(root: Path) -> list[Path]:
    changed_files: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in ROOT_IGNORE for part in p.parts):
            continue
        try:
            text = p.read_text()
        except Exception:
            continue

        if not PATTERN.search(text):
            continue

        new_text = PATTERN.sub(r"\g<prefix>.now(timezone.utc)", text)

        # Ensure timezone import exists (not just a bare substring in the file)
        if not re.search(r"from\s+datetime\s+import\s+.*\btimezone\b", new_text):
            new_text = _ensure_timezone_import(new_text)

        if new_text != text:
            p.write_text(new_text)
            changed_files.append(p)

    return changed_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="Apply replacements in-place"
    )
    parser.add_argument("--root", default=".", help="Root directory to scan")
    parser.add_argument(
        "--report", help="Write a JSON report to the given path (dry-run or apply)"
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    matches = find_matches(root)

    if not matches:
        print("No datetime.utcnow() occurrences found.")
        return 0

    print(f"Found {len(matches)} datetime.utcnow() occurrences:")
    for p, lno, line in matches[:200]:
        print(f" - {p}:{lno}: {line}")

    if args.report:
        report_path = Path(args.report)
        report = [
            {"path": str(p), "line": lno, "content": line} for p, lno, line in matches
        ]
        report_path.write_text(json.dumps(report, indent=2))
        print(f"Wrote report to {report_path}")

    if not args.apply:
        print(
            "\nDry-run: no files modified. Re-run with --apply to update files in-place."
        )
        return 0

    changed = apply_replacements(root)
    print(f"\nApplied replacements to {len(changed)} files:")
    for p in changed:
        print(" - ", p)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
