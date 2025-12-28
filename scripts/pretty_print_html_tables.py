#!/usr/bin/env python3
import re
import sys
from pathlib import Path

TABLE_RE = re.compile(r'(<table[\s\S]*?</table>)', re.IGNORECASE)


def pretty_table_block(block: str) -> str:
    # Insert newlines between adjacent tags to reduce line length
    new = block.replace('><', '>\n<')
    return new


def process_file(p: Path) -> int:
    text = p.read_text(encoding='utf-8')
    new_text, n = TABLE_RE.subn(lambda m: pretty_table_block(m.group(1)), text)
    if n:
        p.write_text(new_text, encoding='utf-8')
        print(f'Pretty-printed {n} table(s) in {p}')
        return n
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: pretty_print_html_tables.py <file1> [file2 ...]')
        sys.exit(2)
    total = 0
    for f in sys.argv[1:]:
        p = Path(f)
        if not p.exists():
            print('Missing', f)
            continue
        total += process_file(p)
    if total == 0:
        print('No changes made')
    else:
        print('Total tables formatted:', total)
    sys.exit(0)