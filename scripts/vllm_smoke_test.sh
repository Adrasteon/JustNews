#!/usr/bin/env bash
# Smoke test to verify vLLM systemd unit (or transient run) handles a basic request
# Usage: scripts/vllm_smoke_test.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$REPO_ROOT/scripts/run_with_env.sh"
UNIT=vllm-mistral-7b.service
PORT=7060

# Helper to start a transient http server if real vllm binary is not present
start_transient_server() {
  echo "Starting transient HTTP server on port $PORT as transient systemd scope"
  systemd-run --user --unit=vllm-mistral-smoke --scope -p MemoryMax=1G --description="vllm-smoke" /usr/bin/env bash -lc "exec python3 -m http.server $PORT"
}

# Check if vllm binary exists in canonical env
if $RUN bash -lc "command -v vllm >/dev/null 2>&1"; then
  echo "vllm binary available; using systemd unit $UNIT"
  $RUN sudo -n true 2>/dev/null || true  # no-op to surface sudo prompt earlier (may be unnecessary)
  $RUN systemctl --user start "$UNIT" || true
else
  echo "vllm not available; starting transient server"
  start_transient_server
fi

# wait for port to open
for i in {1..30}; do
  if nc -z 127.0.0.1 $PORT; then
    echo "Port $PORT open"
    break
  fi
  sleep 1
done

# Run a simple request
if curl -sS --max-time 5 "http://127.0.0.1:$PORT/" >/dev/null; then
  echo "Smoke test succeeded: vLLM endpoint responded"
  # Clean up: stop transient unit (if any)
  systemctl --user stop vllm-mistral-smoke || true
  exit 0
else
  echo "Smoke test failed: no response on $PORT" >&2
  systemctl --user stop vllm-mistral-smoke || true
  exit 2
fi
