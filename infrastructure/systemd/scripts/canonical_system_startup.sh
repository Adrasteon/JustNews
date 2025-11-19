#!/usr/bin/env bash
set -euo pipefail

resolve_root() {
  if [[ -n "${JUSTNEWS_ROOT:-}" ]]; then
    echo "$JUSTNEWS_ROOT"; return 0
  fi
  if [[ -r /etc/justnews/global.env ]]; then
    # shellcheck disable=SC1091
    source /etc/justnews/global.env
    if [[ -n "${JUSTNEWS_ROOT:-}" ]]; then
      echo "$JUSTNEWS_ROOT"; return 0
    fi
    if [[ -n "${SERVICE_DIR:-}" ]]; then
      echo "$SERVICE_DIR"; return 0
    fi
  fi
  echo "${SERVICE_DIR:-/home/adra/JustNews}"
}

ROOT="$(resolve_root)"
SCRIPT="$ROOT/infrastructure/systemd/canonical_system_startup.sh"
if [[ ! -x "$SCRIPT" ]]; then
  echo "canonical_system_startup.sh not found or not executable at $SCRIPT" >&2
  exit 1
fi
# Ensure PYTHONPATH and PYTHON_BIN are exported so downstream services and
# scripts can correctly run using the project's conda environment. If
# `/etc/justnews/global.env` or project `global.env` has been sourced, those
# values will be used; otherwise we prefer the `justnews-v2-py312` conda env
# as a conservative default where available.
export PYTHONPATH="${PYTHONPATH:-$ROOT}"
export PYTHON_BIN="${PYTHON_BIN:-/home/adra/miniconda3/envs/justnews-v2-py312/bin/python}"

exec "$SCRIPT" "$@"
