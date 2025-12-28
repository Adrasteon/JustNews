#!/usr/bin/env python3
"""Add language hints to fenced code blocks missing them using simple heuristics.

Heuristics (applied in order):
- If block contains JSON-ish (starts with '{' or '[' on first non-empty line) -> json
- If block contains YAML-ish (line contains ':' with key-like pattern and no shell keywords) -> yaml
- If block contains shell keywords (sudo, curl, systemctl, docker, conda, python, pip, mysql, journalctl, apt, chmod, chown, etc.) -> bash
- Else leave unchanged

Run cautiously and review diffs.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_FILES = list(ROOT.rglob('*.md'))

SHELL_KEYWORDS = [
    'sudo', 'curl', 'systemctl', 'docker', 'conda', 'python', 'pip', 'mysql', 'journalctl', 'apt',
    'chmod', 'chown', 'grep', 'sed', 'awk', 'cat', 'echo', 'tar', 'install', 'unzip', 'wget'
]


def detect_lang(block: str) -> str | None:
    lines = [l for l in block.splitlines() if l.strip()]
    if not lines:
        return None
    first = lines[0].lstrip()
    # JSON
    if first.startswith('{') or first.startswith('['):
        return 'json'
    # YAML-ish
    for l in lines[:5]:
        if ':' in l and not re.search(r'\$|sudo|conda|python|curl', l):
            # simple heuristic: key: value
            if re.match(r"^\s*[A-Za-z0-9_\-]+\s*:\s*", l):
                return 'yaml'
    # shell
    text = '\n'.join(lines[:20]).lower()
    for kw in SHELL_KEYWORDS:
        if kw in text:
            return 'bash'
    return None


pattern = re.compile(r"(?m)^```\s*$")

changed_files = []
for p in MD_FILES:
    try:
        text = p.read_text(encoding='utf-8')
    except Exception:
        continue
    new = text
    # find opening fences without language
    i = 0
    out = []
    lines = text.splitlines(True)
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^```\s*$", line)
        if m:
            # find closing fence
            j = i + 1
            block_lines = []
            while j < len(lines) and not re.match(r"^```\s*$", lines[j]):
                block_lines.append(lines[j])
                j += 1
            if j < len(lines):
                # we found a closing fence at j
                block = ''.join(block_lines)
                lang = detect_lang(block)
                if lang:
                    out.append(f"```{lang}\n")
                else:
                    out.append(line)
                # append block content
                out.extend(block_lines)
                # append closing fence
                out.append(lines[j])
                i = j + 1
                continue
            else:
                # no closing fence; leave as-is
                out.append(line)
                i += 1
                continue
        else:
            out.append(line)
            i += 1
    new = ''.join(out)
    if new != text:
        p.write_text(new, encoding='utf-8')
        changed_files.append(str(p))

print(f"Updated language hints in {len(changed_files)} files")
for f in changed_files:
    print(f" - {f}")
