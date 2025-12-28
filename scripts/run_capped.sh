#!/usr/bin/env bash
# Usage: scripts/run_capped.sh <MemoryMax> -- <command...>
# Runs a command inside a transient systemd scope with a memory cap.
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <MemoryMax> -- <command...>"
  echo "Example: $0 32G -- pytest -q"
  exit 1
fi

MEM="$1"
shift
if [ "$1" != "--" ]; then
  echo "Usage: $0 <MemoryMax> -- <command...>"
  exit 1
fi
shift

echo "Running command with MemoryMax=${MEM}"
systemd-run --scope -p "MemoryMax=${MEM}" "$@"
