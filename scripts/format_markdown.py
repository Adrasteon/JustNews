#!/usr/bin/env python3
"""Simple Markdown formatter to fix common markdownlint issues:
- Ensure only the first H1 (# ) remains; demote other H1 to H2 (## )
- Ensure blank line before headings
- Ensure blank line before lists
- Remove trailing whitespace
- Collapse >2 consecutive blank lines into 2

Use cautiously; do a git diff review before committing.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MD_FILES = list(ROOT.rglob('*.md'))

def fix_content(text: str) -> str:
    # Normalize line endings
    text = text.replace('\r\n', '\n')

    # Remove trailing spaces
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)

    # Collapse more than 2 blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Ensure there's a blank line before headings (all levels)
    text = re.sub(r"(?m)([^\n])\n(# +)", r"\1\n\n\2", text)

    # Ensure blank line before list items when previous line not blank
    text = re.sub(r"(?m)([^\n])\n(-\s)", r"\1\n\n\2", text)
    text = re.sub(r"(?m)([^\n])\n(\d+\.\s)", r"\1\n\n\2", text)

    # Demote secondary H1s to H2 (only keep first # as H1)
    # We will keep the first occurrence of '^# ' and replace subsequent '^# ' with '## '
    lines = text.split('\n')
    h1_seen = False
    out_lines = []
    for i, line in enumerate(lines):
        if re.match(r"^#\s+", line):
            if not h1_seen:
                h1_seen = True
                out_lines.append(line)
            else:
                # demote one level
                out_lines.append(re.sub(r"^#\s+", "## ", line))
        else:
            out_lines.append(line)
    text = '\n'.join(out_lines)

    # Ensure lists are surrounded by blank lines (again, for safety)
    text = re.sub(r"(?m)([^\n])\n(\s*[-*+]\s)", r"\1\n\n\2", text)

    # Final collapse of excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim trailing whitespace at file ends
    text = text.rstrip() + "\n"
    return text


def main():
    changed = []
    for p in MD_FILES:
        # skip .git and node_modules paths
        if any(part.startswith('.') for part in p.parts):
            # allow README etc but skip dotdirs
            if any(part == '.git' for part in p.parts):
                continue
        try:
            orig = p.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Skipping {p}: {e}")
            continue
        new = fix_content(orig)
        if new != orig:
            p.write_text(new, encoding='utf-8')
            changed.append(str(p))
    print(f"Formatted {len(changed)} files")
    for f in changed:
        print(f" - {f}")

if __name__ == '__main__':
    main()
