#!/usr/bin/env bash
# Start the vLLM systemd unit (user) and wait for it to become active
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Use the env wrapper to ensure canonical env is loaded
RUN="$REPO_ROOT/scripts/run_with_env.sh"
UNIT=${1:-vllm-mistral-7b.service}

echo "Starting $UNIT (user unit)"
$RUN systemctl --user enable --now "$UNIT"
# wait for active
for i in {1..30}; do
  if $RUN systemctl --user is-active --quiet "$UNIT"; then
    echo "$UNIT active"
    exit 0
  fi
  sleep 1
done
echo "Timed out waiting for $UNIT to become active" >&2
systemctl --user status "$UNIT" --no-pager --lines=10 || true
exit 2
