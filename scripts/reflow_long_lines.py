#!/usr/bin/env python3
import sys
from pathlib import Path
import textwrap
import re

TARGET_WIDTH = 120

list_prefix_re = re.compile(r'^(?P<indent>\s*)(?P<prefix>(?:- |\* |\+ |\d+\. ))(?P<body>.*)$')

CODEFenceRe = re.compile(r'^```')


def reflow_text(text: str) -> str:
    lines = text.split('\n')
    out_lines = []
    in_code = False
    for line in lines:
        if CODEFenceRe.match(line):
            in_code = not in_code
            out_lines.append(line)
            continue
        if in_code:
            out_lines.append(line)
            continue
        if 'http://' in line or 'https://' in line or '|' in line:
            out_lines.append(line)
            continue
        if len(line) <= 200:
            out_lines.append(line)
            continue
        # Try to detect list prefix
        m = list_prefix_re.match(line)
        if m:
            indent = m.group('indent')
            prefix = m.group('prefix')
            body = m.group('body').strip()
            subsequent_indent = ' ' * (len(indent) + len(prefix))
            wrapped = textwrap.fill(body, width=TARGET_WIDTH, initial_indent=indent + prefix, subsequent_indent=subsequent_indent)
            out_lines.extend(wrapped.split('\n'))
            continue
        # Otherwise, simple paragraph line
        leading_ws = re.match(r'^(\s*)', line).group(1)
        body = line.strip()
        wrapped = textwrap.fill(body, width=TARGET_WIDTH, initial_indent=leading_ws, subsequent_indent=leading_ws)
        out_lines.extend(wrapped.split('\n'))
    return '\n'.join(out_lines)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: reflow_long_lines.py <file1> [file2 ...]')
        sys.exit(2)
    changed = []
    for f in sys.argv[1:]:
        p = Path(f)
        if not p.exists():
            print('Missing', f)
            continue
        orig = p.read_text(encoding='utf-8')
        new = reflow_text(orig)
        if new != orig:
            p.write_text(new, encoding='utf-8')
            changed.append(f)
            print('Reflowed', f)
    print('Done. Reflowed', len(changed), 'files')
