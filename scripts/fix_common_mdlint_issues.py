#!/usr/bin/env python3
import re
import sys
from pathlib import Path

MD_FILES = list(Path('.').rglob('*.md'))

# Patterns to fix

def fix_text(text: str) -> str:
    # Work outside code fences for inline fixes
    lines = text.split('\n')
    out = []
    in_code = False
    for line in lines:
        if re.match(r'^```', line):
            in_code = not in_code
            # Normalize '``` bash' -> '```bash' and strip trailing spaces
            m = re.match(r'^```\s*([a-zA-Z0-9_+-]+)\s*$', line)
            if m:
                out.append('```' + m.group(1))
            else:
                # remove trailing spaces after fence
                out.append(re.sub(r'```\s+$', '```', line))
            continue
        if in_code:
            # within code block, leave unchanged
            out.append(line)
            continue
        # Remove leading spaces before headings (MD023)
        line = re.sub(r'^[ \t]+(?=#)', '', line)
        # Remove leading spaces before atx-style headings (e.g., ' ##' -> '##')
        line = re.sub(r'^[ \t]+(#{1,6}\s)', r"\1", line)
        # Fix inline code spans with internal leading/trailing spaces (MD038)
        # `  something  ` -> `something`
        line = re.sub(r'`\s+([^`]+?)\s+`', r'`\1`', line)
        line = re.sub(r'`\s+([^`]+?)`', r'`\1`', line)
        line = re.sub(r'`([^`]+?)\s+`', r'`\1`', line)
        # Move stray closing fence on same line to its own line (e.g., "cmd ```" -> "cmd\n```")
        if ' ```' in line and not line.strip().startswith('```'):
            line = line.replace(' ```', '\n```')
        # Replace '``` ' with '```'
        line = re.sub(r'```\s+$', '```', line)
        # Remove empty-link placeholders [Text](#) -> Text (MD042)
        line = re.sub(r'\[([^\]]+?)\]\(\s*#\s*\)', r'\1', line)
        out.append(line)
    return '\n'.join(out)


if __name__ == '__main__':
    changed_files = []
    for p in MD_FILES:
        try:
            orig = p.read_text(encoding='utf-8')
        except Exception:
            continue
        new = fix_text(orig)
        if new != orig:
            p.write_text(new, encoding='utf-8')
            changed_files.append(str(p))
    print('Fixed', len(changed_files), 'files')
    for f in changed_files:
        print(' -', f)
