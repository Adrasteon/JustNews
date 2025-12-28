#!/usr/bin/env python3
import re
import sys
from pathlib import Path

EMAIL_RE = re.compile(r'(?<![<\[])(?P<email>[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![>\]])')


def wrap_file(p: Path) -> int:
    text = p.read_text(encoding='utf-8')
    def repl(m):
        return f'<{m.group("email")}>'
    new_text, n = EMAIL_RE.subn(repl, text)
    if n:
        p.write_text(new_text, encoding='utf-8')
        print(f'Wrapped {n} email(s) in {p}')
        return n
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: wrap_emails.py <file1> [file2 ...]')
        sys.exit(2)
    total = 0
    for f in sys.argv[1:]:
        p = Path(f)
        if not p.exists():
            print('Missing', f)
            continue
        total += wrap_file(p)
    if total == 0:
        print('No changes made')
    else:
        print('Total wrapped:', total)
    sys.exit(0)
