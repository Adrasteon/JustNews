#!/usr/bin/env bash
# Wrapper to run repo boot_smoke_test.sh from a stable path.
# Design: never fail the service (always exit 0); run helper via bash so it
# doesn't depend on execute bit; print a helpful message if missing.
set -uo pipefail

REPO_DIR="/home/adra/justnewsagent/JustNewsAgent"
SCRIPT="$REPO_DIR/deploy/systemd/helpers/boot_smoke_test.sh"

if [[ -r "$SCRIPT" ]]; then
  /usr/bin/env bash "$SCRIPT" || true
  exit 0
else
  echo "[boot-smoke] WARN: boot_smoke_test.sh not found at $SCRIPT (skipping)" >&2
  exit 0
fi
