#!/usr/bin/env python3
"""Targeted fixes for CHANGELOG.md and similar reports:
- Make duplicate headings unique by appending ' (continued N)'
- Ensure fenced code blocks have blank line before/after and a language (default: text)
- Wrap bare URLs (http[s]://...) in angle brackets
- Remove trailing punctuation in headings (colons)
- Convert bold-as-heading lines (e.g., **Step 1: ...**) into proper headings

Use carefully and review diffs.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = [ROOT / 'CHANGELOG.md', ROOT / 'docs' / 'MISTRAL_7B_FP8_OPTIMIZATION_REPORT.md', ROOT / 'docs' / 'operations' / 'VLLM_MISTRAL_7B_SETUP.md']


def ensure_blank_lines_around_fences(lines):
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('```'):
            # ensure previous line is blank
            if out and out[-1].strip() != '':
                out.append('')
            out.append(line)
            i += 1
            # copy until closing fence
            while i < len(lines) and not lines[i].strip().startswith('```'):
                out.append(lines[i])
                i += 1
            if i < len(lines):
                out.append(lines[i])
                i += 1
            # ensure next line is blank
            if i < len(lines) and lines[i].strip() != '':
                out.append('')
        else:
            out.append(line)
            i += 1
    return out


def add_language_to_fences(lines, default='text'):
    out = []
    fence_re = re.compile(r"^(```)(\s*)$")
    for i,line in enumerate(lines):
        m = fence_re.match(line)
        if m:
            out.append('```' + default)
        else:
            out.append(line)
    return out


def wrap_bare_urls(text):
    # Replace bare http(s) urls not already in <> or markdown link
    def repl(m):
        url = m.group(0)
        # don't wrap if already in <...>
        if text[max(0,m.start()-1):m.start()] == '<' and text[m.end():m.end()+1] == '>':
            return url
        return '<' + url + '>'
    return re.sub(r"(?<!\()(?<![<\[])https?://[\w\-\./?%&=#:;,@+~]+", repl, text)


def remove_trailing_colon_from_headings(line):
    return re.sub(r"^(#+\s+.+)\:$", r"\1", line)


def bold_to_heading(line):
    m = re.match(r"^\*\*(.+)\*\*$", line.strip())
    if m:
        content = m.group(1).strip()
        return '### ' + content
    return line


def uniquify_headings(lines):
    seen = {}
    out = []
    heading_re = re.compile(r"^(#{2,})\s*(.+)$")
    for line in lines:
        m = heading_re.match(line)
        if m:
            level = m.group(1)
            text = m.group(2).strip()
            key = text.lower()
            count = seen.get(key, 0)
            if count == 0:
                seen[key] = 1
                out.append(line)
            else:
                seen[key] = count + 1
                out.append(f"{level} {text} (continued {count})")
        else:
            out.append(line)
    return out


def process_file(path: Path):
    text = path.read_text(encoding='utf-8')
    # wrap URLs
    new_text = wrap_bare_urls(text)
    lines = new_text.split('\n')
    # convert bold-as-heading
    lines = [bold_to_heading(l) for l in lines]
    # remove trailing colon in headings
    lines = [remove_trailing_colon_from_headings(l) for l in lines]
    # ensure blank lines around fences
    lines = ensure_blank_lines_around_fences(lines)
    # add default language to bare fences (``` alone) - use 'text'
    lines = add_language_to_fences(lines, default='text')
    # uniquify duplicate headings (for level >=2)
    lines = uniquify_headings(lines)
    result = '\n'.join(lines).rstrip() + '\n'
    if result != text:
        path.write_text(result, encoding='utf-8')
        print(f'Updated {path}')


if __name__ == '__main__':
    for p in TARGETS:
        if p.exists():
            process_file(p)
        else:
            print(f"Missing {p}")
