#!/usr/bin/env python3
"""
Simple repo codemod to replace imports that reference the old
`agents.scout.*` crawl4ai modules with the canonical `agents.c4ai.*` modules.

This script is intentionally conservative: it only rewrites files that
contain the substring `agents.scout` and will show a dry-run by default.

Usage:
  python scripts/codemods/replace_scout_crawl4ai_imports.py [--apply]

When --apply is provided the files will be updated in-place (a .bak copy is
written alongside each changed file). Without --apply the script prints the
proposed changes only.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    # Specific module-level rewrites
    (re.compile(r"\bfrom\s+agents\.scout\.crawl4ai_server_impl\b"), "from agents.c4ai.server"),
    (re.compile(r"\bfrom\s+agents\.scout\.crawl4ai_server\b"), "from agents.c4ai.server"),
    (re.compile(r"\bfrom\s+agents\.scout\.crawl4ai_bridge\b"), "from agents.c4ai.bridge"),
    (re.compile(r"\bimport\s+agents\.scout\.crawl4ai_bridge\b"), "import agents.c4ai.bridge"),
    (re.compile(r"\bimport\s+agents\.scout\.crawl4ai_server\b"), "import agents.c4ai.server"),
    (re.compile(r"\bimport\s+agents\.scout\.crawl4ai_server_impl\b"), "import agents.c4ai.server"),
    # Generic module prefix replacement for any other occurrences like
    # agents.c4ai or agents.c4ai.utils -> agents.c4ai.*
    (re.compile(r"\bagents\.scout\.crawl4ai\b"), "agents.c4ai"),
    (re.compile(r"\bagents\.scout\.crawl4ai_"), "agents.c4ai."),
]


def should_skip_path(path: Path) -> bool:
    s = str(path)
    ignore = [".git/", "__pycache__", "venv/", "env/", ".venv/", "node_modules/", "model_store/"]
    return any(p in s for p in ignore)


def find_python_files(root: Path) -> list[Path]:
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip some large or irrelevant directories early
        if any(part.startswith(".") for part in Path(dirpath).parts):
            continue
        if should_skip_path(Path(dirpath)):
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            results.append(Path(dirpath) / fn)
    return results


def rewrite_text(text: str) -> tuple[str, list[str]]:
    """Apply replacements to text. Returns (new_text, list_of_changes).

    Each change is a short description for reporting.
    """
    changes: list[str] = []
    new = text
    for pattern, repl in REPLACEMENTS:
        if pattern.search(new):
            new2 = pattern.sub(repl, new)
            if new2 != new:
                changes.append(f"{pattern.pattern} -> {repl}")
                new = new2
    return new, changes


def process_file(path: Path, apply: bool) -> tuple[bool, list[str]]:
    text = path.read_text(encoding="utf-8")
    if "agents.scout" not in text:
        return False, []
    new_text, changes = rewrite_text(text)
    if not changes:
        return False, []
    if apply:
        bak = path.with_suffix(path.suffix + ".bak")
        bak.write_text(text, encoding="utf-8")
        path.write_text(new_text, encoding="utf-8")
    return True, changes


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Apply changes in-place (write files).")
    p.add_argument("--root", default=".", help="Root directory to operate on")
    args = p.parse_args(argv)

    root = Path(args.root).resolve()
    py_files = find_python_files(root)

    changed_files: dict[Path, list[str]] = {}

    for f in py_files:
        try:
            changed, changes = process_file(f, apply=args.apply)
            if changed:
                changed_files[f] = changes
        except Exception as e:
            print(f"ERROR processing {f}: {e}")

    if not changed_files:
        print("No files would be changed.")
        return 0

    print("Files changed:")
    for f, ch in sorted(changed_files.items()):
        print(f"- {f}")
        for c in ch:
            print(f"    * {c}")

    if not args.apply:
        print("\nDry-run complete. Re-run with --apply to make these changes.")
    else:
        print("\nApplied changes. Backups written with .bak suffix next to each updated file.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
