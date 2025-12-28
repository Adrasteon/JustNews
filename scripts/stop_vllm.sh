#!/usr/bin/env bash
# Stop the vLLM systemd unit (user)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$REPO_ROOT/scripts/run_with_env.sh"
UNIT=${1:-vllm-mistral-7b.service}

echo "Stopping $UNIT"
$RUN systemctl --user stop "$UNIT" || true
$RUN systemctl --user disable "$UNIT" || true
$RUN systemctl --user is-active --quiet "$UNIT" && (echo "Failed to stop $UNIT"; exit 2) || echo "$UNIT stopped"
