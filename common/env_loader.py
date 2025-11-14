"""Utility helpers for loading environment variables from global.env.

This provides a shared implementation so that scripts run outside the
systemd-managed stack can still discover credentials defined in the
standard ``global.env`` file.  Values from existing environment variables
always take precedence so that explicit exports override file contents.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Sequence

_LOADED_ENV_PATHS: set[Path] = set()


def _iter_candidate_paths(extra_paths: Sequence[Path] | None = None) -> List[Path]:
    """Return candidate locations for the global environment file."""
    candidates: list[Path] = []

    env_override = os.environ.get("JUSTNEWS_GLOBAL_ENV")
    if env_override:
        candidates.append(Path(env_override).expanduser())

    # Standard system location used by the managed services.
    candidates.append(Path("/etc/justnews/global.env"))

    # If SERVICE_DIR is defined we expect a sibling global.env next to it.
    service_dir = os.environ.get("SERVICE_DIR")
    if service_dir:
        candidates.append(Path(service_dir).expanduser() / "global.env")

    # Repository root – this module lives in common/, so parents[1] is the
    # package directory and parents[2] is the repo root.
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / "global.env")

    # Current working directory for ad-hoc scripts.
    candidates.append(Path.cwd() / "global.env")

    if extra_paths:
        candidates.extend(extra_paths)

    # Remove duplicates while preserving order.
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def load_global_env(*, logger=None, extra_paths: Iterable[Path] | None = None) -> list[Path]:
    """Load environment variables from the first accessible global.env files.

    Returns a list of paths that were successfully loaded.  The same file is
    never processed more than once per process.
    """
    loaded: list[Path] = []
    extras = list(extra_paths or [])
    for path in _iter_candidate_paths(extras):
        if path in _LOADED_ENV_PATHS:
            continue
        if not path.exists() or not path.is_file():
            continue

        try:
            with open(path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Strip surrounding quotes and inline comments if present.
                    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
                        value = value[1:-1]
                    if " #" in value:
                        value = value.split(" #", 1)[0].strip()
                    if key and key not in os.environ:
                        os.environ[key] = value
            _LOADED_ENV_PATHS.add(path)
            loaded.append(path)
            if logger:
                logger.info("Loaded environment variables from %s", path)
        except Exception as exc:  # pragma: no cover - defensive
            if logger:
                logger.warning("Failed to load environment file %s: %s", path, exc)
            continue

    return loaded


__all__ = ["load_global_env"]
