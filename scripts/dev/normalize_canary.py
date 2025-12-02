#!/usr/bin/env python3
"""Simple canary normalizer for smoke tests.

Reads JSON records from `output/canary_raw/*.json`, computes a normalized URL
using `common.url_normalization.normalize_article_url`, and writes a normalized
JSON record to `output/canary_normalized/`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List
from datetime import datetime

from common.url_normalization import normalize_article_url


RAW_DIR = Path.cwd() / "output" / "canary_raw"
OUT_DIR = Path.cwd() / "output" / "canary_normalized"


def find_raw_files() -> List[Path]:
    return sorted(RAW_DIR.glob("*.json")) if RAW_DIR.exists() else []


def normalize_file(path: Path) -> Path:
    data = json.loads(path.read_text(encoding="utf-8"))
    url = data.get("url") or ""
    normalized = normalize_article_url(url)
    out = {
        "url": url,
        "normalized_url": normalized,
        "normalized_at": datetime.utcnow().isoformat() + "Z",
        "status_code": data.get("status_code"),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / path.name
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main():
    files = find_raw_files()
    return [str(normalize_file(p)) for p in files]


if __name__ == "__main__":
    items = main()
    for i in items:
        print(i)
