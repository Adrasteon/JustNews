#!/usr/bin/env python3
import re
import sys
from pathlib import Path

# Join URLs broken with hyphen-linebreaks like '...open-\nto-the-...' -> '...open-to-the-...'
BROKEN_HYPHEN_URL = re.compile(r"(https?://[^\s\n]+)-\s*\n\s*([A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+)")
# Fix links broken between 'https:/' and '/rest-of-path' where newline split the initial '//'
BROKEN_SLASH_URL = re.compile(r"(https?):/\s*\n\s*/")


def fix_file(p: Path) -> int:
    text = p.read_text(encoding='utf-8')
    total = 0
    new_text, n = BROKEN_HYPHEN_URL.subn(r"\1-\2", text)
    if n:
        total += n
        text = new_text
    # Fix 'https:/\n//domain/path' -> 'https://domain/path'
    new_text, n = BROKEN_SLASH_URL.subn(r"\1://", text)
    if n:
        total += n
        text = new_text
    # Remove stray spaces inside URLs (e.g., '...using- jax-flax...' or '...embedding-model-ever-with-1b-training-pairs/7354)')
    # Iteratively collapse whitespace inside sequences that start with 'http' until no change
    WHITESPACE_IN_URL = re.compile(r"(https?://[^\s\)\]>]*?)\s+([^\s\)\]>]+)")
    while True:
        new_text, n = WHITESPACE_IN_URL.subn(r"\1\2", text)
        if n == 0:
            break
        total += n
        text = new_text

    if total:
        p.write_text(text, encoding='utf-8')
        print(f'Fixed {total} broken URL(s) in {p}')
        return total
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: fix_broken_urls.py <file1> [file2 ...]')
        sys.exit(2)
    total = 0
    for f in sys.argv[1:]:
        p = Path(f)
        if not p.exists():
            print('Missing', f)
            continue
        total += fix_file(p)
    if total == 0:
        print('No fixes made')
    else:
        print('Total fixes:', total)
    sys.exit(0)
