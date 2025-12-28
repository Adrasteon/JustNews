#!/usr/bin/env python3
"""Normalize top-level unordered checklist indents by removing 2 leading spaces
for lines starting with two spaces followed by '- ' or '- ['. Skips code fences.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
# Target all markdown files under 'docs' and top-level checklists/quick refs
FILES = list(ROOT.rglob('*.md'))
# Optionally exclude certain paths
EXCLUDE = ['.git', 'node_modules', 'models']
# Filter files
FILES = [p for p in FILES if not any(ex in str(p) for ex in EXCLUDE)]

for p in FILES:
    if not p.exists():
        continue
    text = p.read_text(encoding='utf-8')
    lines = text.splitlines()
    out = []
    in_code = False
    changed = False
    for line in lines:
        if line.strip().startswith('```'):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        # Replace leading two spaces for top-level checklist lines
        m = re.match(r'^\s{2}(-\s\[\s?\]|-\s)', line)
        if m:
            new = re.sub(r'^\s{2}', '', line)
            out.append(new)
            changed = True
        else:
            out.append(line)
    new_text = '\n'.join(out) + '\n'
    if changed:
        p.write_text(new_text, encoding='utf-8')
        print(f'Normalized list indents in {p}')
    else:
        print(f'No changes needed for {p}')
