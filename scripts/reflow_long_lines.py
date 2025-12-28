#!/usr/bin/env python3
import sys
from pathlib import Path
import textwrap
import re

TARGET_WIDTH = 120

list_prefix_re = re.compile(r'^(?P<indent>\s*)(?P<prefix>(?:- |\* |\+ |\d+\. ))(?P<body>.*)$')

CODEFenceRe = re.compile(r'^```')
URL_RE = re.compile(r'https?://[^\s)\]>]+')


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
        # Skip tables
        if '|' in line:
            out_lines.append(line)
            continue
        # Only reflow long lines; but handle URLs by replacing with tokens so they aren't split
        if len(line) <= TARGET_WIDTH:
            out_lines.append(line)
            continue

        # Replace URLs with placeholders to avoid splitting them
        urls = []
        def _url_repl(m):
            idx = len(urls)
            urls.append(m.group(0))
            return f"__URL{idx}__"

        placeholder_line = URL_RE.sub(_url_repl, line)

        # Try to detect list prefix
        m = list_prefix_re.match(placeholder_line)
        if m:
            indent = m.group('indent')
            prefix = m.group('prefix')
            body = m.group('body').strip()
            subsequent_indent = ' ' * (len(indent) + len(prefix))
            wrapped = textwrap.fill(body, width=TARGET_WIDTH, initial_indent=indent + prefix, subsequent_indent=subsequent_indent)
            parts = wrapped.split('\n')
        else:
            leading_ws = re.match(r'^(\s*)', placeholder_line).group(1)
            body = placeholder_line.strip()
            wrapped = textwrap.fill(body, width=TARGET_WIDTH, initial_indent=leading_ws, subsequent_indent=leading_ws)
            parts = wrapped.split('\n')

        # Restore URLs in each wrapped line
        restored = []
        for part in parts:
            for i, u in enumerate(urls):
                part = part.replace(f"__URL{i}__", u)
            restored.append(part)
        out_lines.extend(restored)
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
