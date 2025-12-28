#!/usr/bin/env bash
# Usage: scripts/safe_local_run.sh -- <command...>
# Sets safe env defaults for local dev to avoid GPU OOMs and fragmentation issues
set -euo pipefail

# Default safe values (can be overridden in caller environment)
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export VLLM_SKIP_START="${VLLM_SKIP_START:-1}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

# Show what we're setting (brief)
echo "[safe_local_run] CUDA_VISIBLE_DEVICES='${CUDA_VISIBLE_DEVICES:-unset}' VLLM_SKIP_START='${VLLM_SKIP_START}' PYTORCH_CUDA_ALLOC_CONF='${PYTORCH_CUDA_ALLOC_CONF}'"

# Find the command after the '--'
if [ "$#" -eq 0 ]; then
  echo "Usage: $0 -- <command...>"
  exit 1
fi

# If the first argument is '--', shift it
if [ "$1" = "--" ]; then
  shift
fi

if [ "$#" -eq 0 ]; then
  echo "No command specified. Usage: $0 -- <command...>"
  exit 1
fi

exec "$@"
