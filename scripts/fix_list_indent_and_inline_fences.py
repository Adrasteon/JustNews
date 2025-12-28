#!/usr/bin/env python3
import re
from pathlib import Path

MD_FILES = list(Path('.').rglob('*.md'))

INLINE_FENCE_RE = re.compile(r'(```)([^`\n]*?)\1')


def fix_file(text: str) -> str:
    # First, fix inline fences that appear on the same line
    def repl_inline(m):
        content = m.group(2).strip()
        # If content is empty, keep as is
        if content == '':
            return '```\n```'
        # If content contains '```' then skip
        if '```' in content:
            return m.group(0)
        return '```\n' + content + '\n```'

    text = INLINE_FENCE_RE.sub(repl_inline, text)

    # Now fix list indentation: change leading 4 spaces before list items to 2 spaces
    lines = text.split('\n')
    out = []
    in_code = False
    for line in lines:
        if re.match(r'^```', line):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        # replace leading 4 spaces before list markers with 2 spaces
        newline = re.sub(r'^(\s{4,})([-*+])\s+', lambda m: '  ' + m.group(2) + ' ', line)
        out.append(newline)
    return '\n'.join(out)


if __name__ == '__main__':
    changed = []
    for p in MD_FILES:
        try:
            orig = p.read_text(encoding='utf-8')
        except Exception:
            continue
        new = fix_file(orig)
        if new != orig:
            p.write_text(new, encoding='utf-8')
            changed.append(str(p))
    print('Fixed', len(changed), 'files')
    for f in changed:
        print(' -', f)
