#!/usr/bin/env python3
import re
import sys
from pathlib import Path

URL_RE = re.compile(r'(?P<prefix>^|(?<=\s)|(?<=\()|(?<=\.)|(?<=\-))(?P<url>https?://[^\s)\]>]+)')


def wrap_file(p: Path) -> int:
    text = p.read_text(encoding='utf-8')
    changed = False

    def repl(m):
        prefix = m.group('prefix') or ''
        url = m.group('url')
        # Skip if already wrapped or part of markdown link
        start = m.start('url')
        end = m.end('url')
        if start > 0 and text[start-1] in '[<(':
            return m.group(0)
        if text[start-1:start+1].startswith('!['):
            return m.group(0)
        # If already angle-bracketed on right
        if end < len(text) and text[end] == '>':
            return m.group(0)
        return prefix + f'<{url}>'

    new_text = URL_RE.sub(repl, text)
    if new_text != text:
        p.write_text(new_text, encoding='utf-8')
        return 1
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: wrap_bare_urls.py <file1> [file2 ...]')
        sys.exit(2)
    total = 0
    for f in sys.argv[1:]:
        p = Path(f)
        if not p.exists():
            print('Missing', f)
            continue
        changed = wrap_file(p)
        if changed:
            print('Wrapped URLs in', f)
            total += changed
    if total == 0:
        print('No changes made')
    sys.exit(0)
