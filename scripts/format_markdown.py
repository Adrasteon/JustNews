#!/usr/bin/env python3
"""Simple Markdown formatter to fix common markdownlint issues:
- Ensure only the first H1 (# ) remains; demote other H1 to H2 (## )
- Ensure blank line before headings
- Ensure blank line before lists
- Remove trailing whitespace
- Collapse >2 consecutive blank lines into 2

Use cautiously; do a git diff review before committing.
"""
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MD_FILES = list(ROOT.rglob('*.md'))

def fix_content(text: str) -> str:
    # Normalize line endings
    text = text.replace('\r\n', '\n')

    # Remove trailing spaces
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)

    # Collapse more than 2 blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Ensure there's a blank line before headings (all levels)
    text = re.sub(r"(?m)([^\n])\n(# +)", r"\1\n\n\2", text)

    # Ensure blank line before list items when previous line not blank
    text = re.sub(r"(?m)([^\n])\n(-\s)", r"\1\n\n\2", text)
    text = re.sub(r"(?m)([^\n])\n(\d+\.\s)", r"\1\n\n\2", text)

    # Normalize ordered list prefixes to '1.' (markdownlint preferred style)
    text = re.sub(r"(?m)^(\s*)\d+\.\s", lambda m: m.group(1) + '1. ', text)

    # Ensure there's a blank line after headings (some lint rules expect it)
    text = re.sub(r"(?m)^(#{1,6}.+)\n(?!\n|$)", r"\1\n\n", text)

    # Ensure fenced code blocks are surrounded by blank lines
    text = re.sub(r"(?m)([^\n])\n(```)", r"\1\n\n\2", text)
    text = re.sub(r"(?m)(^```\s*$)\n(?!\n|$)", r"\1\n\n", text)

    # Demote secondary H1s to H2 (only keep first # as H1)
    # We will keep the first occurrence of '^# ' and replace subsequent '^# ' with '## '
    lines = text.split('\n')
    h1_seen = False
    out_lines = []
    for i, line in enumerate(lines):
        if re.match(r"^#\s+", line):
            if not h1_seen:
                h1_seen = True
                out_lines.append(line)
            else:
                # demote one level
                out_lines.append(re.sub(r"^#\s+", "## ", line))
        else:
            out_lines.append(line)
    text = '\n'.join(out_lines)

    # Ensure lists are surrounded by blank lines (again, for safety)
    text = re.sub(r"(?m)([^\n])\n(\s*[-*+]\s)", r"\1\n\n\2", text)

    # Final collapse of excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Add language hint for code fences without language if they look like shell snippets
    lines = text.split('\n')
    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^```\s*$", line):
            # peek next non-empty line
            j = i + 1
            next_line = ''
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines):
                next_line = lines[j]
            if next_line and (next_line.strip().startswith('$') or any(k in next_line for k in ['conda ', 'bash ', 'curl ', 'sudo ', 'python ', 'pip ', 'docker ', 'systemctl', 'journalctl', 'mysql ', 'mysql -u'])):
                out_lines.append('```bash')
                i += 1
                continue
        out_lines.append(line)
        i += 1
    text = '\n'.join(out_lines)

    # Normalize hard tabs and list indentation (outside code blocks)
    lines = text.split('\n')
    out_lines = []
    in_code = False
    for line in lines:
        if re.match(r"^```", line):
            in_code = not in_code
            out_lines.append(line)
            continue
        if in_code:
            out_lines.append(line)
            continue
        # Replace hard tabs with two spaces
        if '\t' in line:
            line = line.replace('\t', '  ')
        # Normalize leading space counts for list markers to even numbers (0,2,4...)
        m = re.match(r"^(\s+)([-*+]\s+)(.*)", line)
        if m:
            spaces = m.group(1)
            count = len(spaces)
            desired = count if count % 2 == 0 else max(0, count - 1)
            line = (' ' * desired) + m.group(2) + m.group(3)
        else:
            # ordered lists
            m2 = re.match(r"^(\s+)(\d+\.\s+)(.*)", line)
            if m2:
                spaces = m2.group(1)
                count = len(spaces)
                desired = count if count % 2 == 0 else max(0, count - 1)
                line = (' ' * desired) + m2.group(2) + m2.group(3)
        out_lines.append(line)
    text = '\n'.join(out_lines)

    # Wrap long paragraph lines (outside code blocks) to 80 chars
    wrapped = []
    in_code = False
    para = []

    def _flush_para(p):
        if not p:
            return []
        s = ' '.join(l.strip() for l in p)
        # Wrap paragraphs to 120 columns to keep lines readable while allowing
        # longer documentation lines for planning/ops files.
        wrapped_text = textwrap.fill(s, width=120)
        return wrapped_text.split('\n')

    for line in text.split('\n'):
        if re.match(r"^```", line):
            if para:
                wrapped.extend(_flush_para(para))
                para = []
            in_code = not in_code
            wrapped.append(line)
            continue
        if in_code:
            wrapped.append(line)
            continue
        if line.strip() == '':
            if para:
                wrapped.extend(_flush_para(para))
                para = []
            wrapped.append(line)
            continue
        # Heading or list or blockquote – flush paragraph first
        if re.match(r"^\s*(#{1,6}\s+|[-*>+]\s+|\d+\.\s+)", line):
            if para:
                wrapped.extend(_flush_para(para))
                para = []
            wrapped.append(line)
            continue
        para.append(line)

    if para:
        wrapped.extend(_flush_para(para))

    text = '\n'.join(wrapped)

    # Trim trailing whitespace at file ends
    text = text.rstrip() + "\n"
    return text


def main():
    changed = []
    for p in MD_FILES:
        # skip .git and node_modules paths
        if any(part.startswith('.') for part in p.parts):
            # allow README etc but skip dotdirs
            if any(part == '.git' for part in p.parts):
                continue
        try:
            orig = p.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Skipping {p}: {e}")
            continue
        new = fix_content(orig)
        if new != orig:
            p.write_text(new, encoding='utf-8')
            changed.append(str(p))
    print(f"Formatted {len(changed)} files")
    for f in changed:
        print(f" - {f}")

if __name__ == '__main__':
    main()
