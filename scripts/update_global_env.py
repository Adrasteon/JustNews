#!/usr/bin/env python3
"""Utility to update the sibling global.env with model store settings.

Run from the repository root:
    python3 scripts/update_global_env.py [--path /custom/global.env]
"""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent
    default_path = repo_root.parent / "global.env"
    parser = argparse.ArgumentParser(
        description="Update system global.env with model store vars"
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=default_path,
        help="Path to the global.env file (defaults to sibling global.env)",
    )
    return parser.parse_args()


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"global.env not found: {path}")
    return path.read_text(encoding="utf-8").splitlines()


def find_key_indexes(lines: list[str]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _ = stripped.split("=", 1)
        indexes[key] = idx
    return indexes


def ensure_trailing_blank(lines: list[str]) -> None:
    if lines and lines[-1].strip():
        lines.append("")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    args = parse_args()
    global_env_path = args.path

    target_values = {
        "MODEL_STORE_ROOT": str((repo_root / "model_store").resolve()),
        "BASE_MODEL_DIR": str(repo_root.resolve()),
        "MARIADB_PASSWORD": "password123",
    }

    lines = load_lines(global_env_path)
    indexes = find_key_indexes(lines)
    updated = False

    for key, value in target_values.items():
        new_line = f"{key}={value}"
        if key in indexes:
            if lines[indexes[key]] != new_line:
                lines[indexes[key]] = new_line
                updated = True
        else:
            if not updated:
                ensure_trailing_blank(lines)
            lines.append(new_line)
            updated = True

    if not updated:
        print(f"No changes needed for {global_env_path}")
        return

    global_env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Updated {global_env_path} with model store settings")


if __name__ == "__main__":
    main()
