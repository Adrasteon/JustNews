#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MANIFEST_FILE="${MANIFEST_OVERRIDE:-$REPO_ROOT/infrastructure/agents_manifest.sh}"
if [ -f "$MANIFEST_FILE" ]; then
  # shellcheck disable=SC1090
  . "$MANIFEST_FILE"
else
  echo "WARNING: could not find agents manifest at $MANIFEST_FILE; falling back to static AGENT_PORTS"
fi
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

AGENT_PORTS=()
for e in "${AGENTS_MANIFEST[@]:-}"; do
  IFS='|' read -r _name _module port <<< "$e"
  AGENT_PORTS+=("$port")
done

# Export helpful env vars derived from manifests to be consistent with start script
if [ -n "${AGENTS_MANIFEST:+x}" ]; then
  for e in "${AGENTS_MANIFEST[@]}"; do
    IFS='|' read -r name module port <<< "$e"
    case "$name" in
      mcp_bus)
        export MCP_BUS_URL="http://localhost:$port"
        ;;
    esac
  done
fi
if [ -n "${INFRA_MANIFEST:+x}" ]; then
  for e in "${INFRA_MANIFEST[@]}"; do
    IFS='|' read -r name desc port <<< "$e"
    case "$name" in
      mariadb)
        export MARIADB_PORT="$port"
        ;;
      chromadb)
        export CHROMADB_PORT="$port"
        ;;
      crawl4ai)
        export CRAWL4AI_PORT="$port"
        ;;
      grafana)
        export GRAFANA_PORT="$port"
        ;;
      prometheus)
        export PROMETHEUS_PORT="$port"
        ;;
      node_exporter)
        export NODE_EXPORTER_PORT="$port"
        ;;
      dcgm_exporter)
        export DCGM_EXPORTER_PORT="$port"
        ;;
    esac
  done
fi

is_port_in_use() {
  local port="$1"
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    return 0
  fi
  return 1
}

attempt_shutdown_port() {
  local port="$1"
  local url="http://localhost:${port}/shutdown"
  if command -v curl >/dev/null 2>&1; then
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST --max-time 3 "$url" || true)
    if [ "$code" = "200" ] || [ "$code" = "202" ] || [ "$code" = "204" ]; then
      echo "Shutdown endpoint accepted POST on $port (code $code)"
      return 0
    fi
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url" || true)
    if [ "$code" = "200" ] || [ "$code" = "202" ] || [ "$code" = "204" ]; then
      echo "Shutdown endpoint accepted GET on $port (code $code)"
      return 0
    fi
  fi
  return 1
}

free_port_force() {
  local port="$1"
  echo "Attempting to free port $port by killing process(es)"
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti tcp:"$port" || true)
  fi
  if [ -z "$pids" ]; then
    pids=$(ss -ltnp 2>/dev/null | grep -E ":[.]?$port\b" | sed -n 's/.*pid=\([0-9]*\),.*/\1/p' | tr '\n' ' ')
  fi
  if [ -z "$pids" ]; then
    echo "No PID found for port $port; nothing to kill"
    return 1
  fi
  for pid in $pids; do
    echo "Sending TERM to pid $pid (port $port)"
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 3
  if is_port_in_use "$port"; then
    echo "Port $port still in use; sending SIGKILL to PIDs: $pids"
    for pid in $pids; do
      kill -9 "$pid" 2>/dev/null || true
    done
    sleep 1
  fi
  if is_port_in_use "$port"; then
    echo "Failed to free port $port"
    return 1
  fi
  echo "Port $port freed"
  return 0
}

for port in "${AGENT_PORTS[@]}"; do
  if is_port_in_use "$port"; then
    echo "Attempting graceful shutdown of service on port $port"
    if attempt_shutdown_port "$port"; then
      echo "Shutdown accepted on $port"
      sleep 2
      continue
    fi
    echo "Graceful shutdown failed for $port; forcing cleanup"
    free_port_force "$port" || echo "Warning: could not free port $port"
  else
    echo "Port $port not in use"
  fi
done

echo "Stop sequence complete. Check logs in $LOG_DIR for per-agent details."
