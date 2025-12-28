#!/usr/bin/env bash
# Wait for vLLM to be ready (health and /v1/models); optionally accepts API key
# Usage: wait_for_vllm.sh [--base-url http://127.0.0.1:7060] [--api-key KEY] [--timeout 30]
set -euo pipefail

BASE_URL="http://127.0.0.1:7060"
API_KEY=""
TIMEOUT=30

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2;;
    --api-key) API_KEY="$2"; shift 2;;
    --timeout) TIMEOUT="$2"; shift 2;;
    -h|--help) echo "Usage: $0 [--base-url URL] [--api-key KEY] [--timeout SECONDS]"; exit 0;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

END=$(( $(date +%s) + TIMEOUT ))
HEADERS=( -s )
if [[ -n "$API_KEY" ]]; then
  HEADERS+=( -H "Authorization: Bearer $API_KEY" )
fi

while [[ $(date +%s) -lt $END ]]; do
  # Check /health
  if curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    # Try models endpoint (may be auth protected)
    if curl -s ${HEADERS[@]} "$BASE_URL/v1/models" >/dev/null 2>&1; then
      echo "vLLM is ready"
      exit 0
    fi
  fi
  sleep 1
done

echo "Timeout waiting for vLLM at $BASE_URL" >&2
exit 1
