#!/usr/bin/env python3
import sys
from pathlib import Path


def process_file(p: Path) -> int:
    text = p.read_text(encoding='utf-8')
    new_text = text.replace('> <', '>\n<')
    if new_text != text:
        p.write_text(new_text, encoding='utf-8')
        print(f'Split adjacent HTML tags in {p}')
        return 1
    print('No changes made')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: split_adjacent_html_tags.py <file1> [file2 ...]')
        sys.exit(2)
    total = 0
    for f in sys.argv[1:]:
        p = Path(f)
        if not p.exists():
            print('Missing', f)
            continue
        total += process_file(p)
    print('Total files modified:', total)
    sys.exit(0)