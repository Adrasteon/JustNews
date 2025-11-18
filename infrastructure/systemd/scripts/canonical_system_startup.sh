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

exec "$SCRIPT" "$@"
