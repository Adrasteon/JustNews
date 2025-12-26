#!/usr/bin/env python3
"""Codemod to replace Pydantic `.dict()` calls with `.model_dump()`.

This tool is conservative and avoids touching common false-positives like
`patch.dict(...)`. It performs a textual replacement of `.dict(` to `.model_dump(`
for likely model instances.

Usage: python scripts/codemods/replace_pydantic_dict.py [--apply] [--root PATH] [--report PATH]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT_IGNORE = {".git", "node_modules", "third_party", "__pycache__", "tests/deprecation", "tests/codemod", "deprecations", "codemods"}

PATTERN = re.compile(r"\.dict\(")


def _find_files(root: Path) -> list[Path]:
    results: list[Path] = []
    for p in root.rglob("*.py"):
        if any(ignore in str(p) for ignore in ROOT_IGNORE):
            continue
        results.append(p)
    return results


def _should_skip(line: str, start: int) -> bool:
    # If the match is part of `patch.dict(` or similar, skip
    prefix = line[:start]
    if re.search(r"patch\.$", prefix.strip()):
        return True
    # common pattern: with patch.dict(...)
    if "patch.dict(" in line:
        return True
    # If this line contains an explicit hasattr(model, 'model_dump') pattern we shouldn't
    # blindly replace the fallback `.dict()` call (it would create a broken call).
    if "hasattr(" in line:
        return True
    return False


def find_matches(root: Path) -> list[tuple[Path, int, str]]:
    matches: list[tuple[Path, int, str]] = []
    for p in _find_files(root):
        try:
            text = p.read_text()
        except Exception:
            continue

        for i, line in enumerate(text.splitlines(), start=1):
            for m in PATTERN.finditer(line):
                if _should_skip(line, m.start()):
                    continue
                matches.append((p, i, line.rstrip()))
    return matches


def apply_replacements(root: Path) -> list[Path]:
    changed: list[Path] = []
    for p in _find_files(root):
        try:
            text = p.read_text()
        except Exception:
            continue

        new_lines: list[str] = []
        changed_file = False
        for line in text.splitlines():
            newline = line
            for m in list(PATTERN.finditer(line)):
                if _should_skip(line, m.start()):
                    continue
                newline = newline.replace('.dict(', '.model_dump(')
                changed_file = True
            new_lines.append(newline)

        if changed_file:
            p.write_text('\n'.join(new_lines) + '\n')
            changed.append(p)

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default='.', help="Root dir to scan")
    parser.add_argument("--apply", action='store_true', help="Apply in-place")
    parser.add_argument("--report", help="Write JSON report path")
    args = parser.parse_args(argv)

    root = Path(args.root)
    matches = find_matches(root)
    if not matches:
        print("No .dict() occurrences found (excluding patch.dict).")
        return 0

    print(f"Found {len(matches)} .dict() occurrences (candidates):")
    for p, lno, line in matches[:200]:
        print(f" - {p}:{lno}: {line}")

    if args.report:
        Path(args.report).write_text(json.dumps([{"path": str(p), "line": lno, "content": line} for p, lno, line in matches], indent=2))
        print(f"Wrote report to {args.report}")

    if not args.apply:
        print("\nDry-run: no files modified. Re-run with --apply to update files in-place.")
        return 0

    changed = apply_replacements(root)
    print(f"\nApplied replacements to {len(changed)} files:")
    for c in changed:
        print(" - ", c)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
