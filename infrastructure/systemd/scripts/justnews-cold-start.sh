#!/bin/bash
# Wrapper to run repo cold_start.sh from a stable path
set -euo pipefail
REPO_DIR="/home/adra/justnewsagent/JustNewsAgent"
SCRIPT="$REPO_DIR/deploy/systemd/cold_start.sh"
if [[ -x "$SCRIPT" ]]; then
  exec sudo -n "$SCRIPT"
else
  echo "cold_start.sh not found or not executable at $SCRIPT" >&2
  exit 1
fi
