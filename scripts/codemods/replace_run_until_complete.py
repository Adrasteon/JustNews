#!/usr/bin/env python3
"""Codemod to replace common run_until_complete patterns with asyncio.run()

Behavior:
 - Replaces `asyncio.get_event_loop().run_until_complete(expr)` -> `asyncio.run(expr)`
 - Replaces `loop.run_until_complete(expr)` -> `asyncio.run(expr)` when the file
   contains a `asyncio.new_event_loop()` call (heuristic indicating the loop is local)

This is conservative — it avoids replacing `loop.run_until_complete` when we can't
determine that `loop` comes from `asyncio.new_event_loop()` in the same file.

Usage: python scripts/codemods/replace_run_until_complete.py [--apply] [--root PATH] [--report PATH]
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

# Match asyncio.get_event_loop().run_until_complete(xxx)
GET_LOOP_PATTERN = re.compile(
    r"asyncio\.get_event_loop\(\)\.run_until_complete\(([^\)]*)\)"
)

# Match <name>.run_until_complete(expr) — we'll replace only when the file contains new_event_loop
LOOP_RUN_PATTERN = re.compile(r"\b(?P<var>\w+)\.run_until_complete\(([^\)]*)\)")
ASSIGN_PATTERN = re.compile(
    r"(?P<var>\w+)\s*=\s*asyncio\.(?:new_event_loop|get_event_loop)\(\)"
)


def _find_files(root: Path) -> list[Path]:
    results = []
    for p in root.rglob("*.py"):
        if any(ignore in str(p) for ignore in ROOT_IGNORE):
            continue
        results.append(p)
    return results


def find_matches(root: Path) -> list[tuple[Path, int, str]]:
    matches: list[tuple[Path, int, str]] = []
    for p in _find_files(root):
        try:
            text = p.read_text()
        except Exception:
            continue

        # Identify assignment to loop variables (e.g. "loop = asyncio.new_event_loop()" or
        # "loop = asyncio.get_event_loop()") so we can safely replace var.run_until_complete
        # NOTE: assigned_vars is computed in apply_replacements where it is actually used

        for i, line in enumerate(text.splitlines(), start=1):
            if GET_LOOP_PATTERN.search(line) or LOOP_RUN_PATTERN.search(line):
                matches.append((p, i, line.rstrip()))

    return matches


def apply_replacements(root: Path) -> list[Path]:
    changed: list[Path] = []
    for p in _find_files(root):
        try:
            text = p.read_text()
        except Exception:
            continue

        if not (GET_LOOP_PATTERN.search(text) or LOOP_RUN_PATTERN.search(text)):
            continue

        new_text = text

        # Replace direct get_event_loop().run_until_complete(...)
        new_text = GET_LOOP_PATTERN.sub(r"asyncio.run(\1)", new_text)

        # For var.run_until_complete(...) only replace when we detected the variable was
        # assigned from asyncio.new_event_loop() or asyncio.get_event_loop() earlier
        assigned_vars = {m.group("var") for m in ASSIGN_PATTERN.finditer(text)}
        if assigned_vars:

            def _sub_var(match: re.Match, assigned_vars=assigned_vars) -> str:
                var = match.group("var")
                inner = match.group(2)
                if var in assigned_vars:
                    return f"asyncio.run({inner})"
                return match.group(0)

            new_text = LOOP_RUN_PATTERN.sub(_sub_var, new_text)

        if new_text != text:
            p.write_text(new_text)
            changed.append(p)

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Root dir to scan")
    parser.add_argument("--apply", action="store_true", help="Apply in-place")
    parser.add_argument("--report", help="Write JSON report path")
    args = parser.parse_args(argv)

    root = Path(args.root)

    matches = find_matches(root)
    if not matches:
        print("No run_until_complete occurrences found.")
        return 0

    print(f"Found {len(matches)} run_until_complete occurrences:")
    for p, lno, line in matches[:200]:
        print(f" - {p}:{lno}: {line}")

    if args.report:
        report = [
            {"path": str(p), "line": lno, "content": line} for p, lno, line in matches
        ]
        Path(args.report).write_text(json.dumps(report, indent=2))
        print(f"Wrote report to {args.report}")

    if not args.apply:
        print(
            "\nDry-run: no files modified. Re-run with --apply to update files in-place."
        )
        return 0

    changed = apply_replacements(root)
    print(f"\nApplied replacements to {len(changed)} files:")
    for c in changed:
        print(" - ", c)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
