#!/usr/bin/env bash
# integration_smoke_test.sh — Minimal manifest-driven start→smoke→stop test

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

MANIFEST_FILE="$TMPDIR/test_manifest.sh"
GLOBAL_ENV="$TMPDIR/global.env"
CONDA_SHIM="$TMPDIR/conda"
LOG_DIR="$SCRIPT_DIR/logs/integration-smoke"
mkdir -p "$LOG_DIR"

# Minimal test manifest that starts mcp_bus and a single test agent
cat > "$MANIFEST_FILE" <<'EOF'
AGENTS_MANIFEST=(
  "mcp_bus|agents.mcp_bus.main:app|8000"
  "test_agent|agents.test_echo.main:app|8765"
)
INFRA_MANIFEST=(
  "grafana|Grafana UI|3000"
)
export AGENTS_MANIFEST INFRA_MANIFEST
export GRAFANA_PORT=3000
EOF

# Minimal global.env that will be read by systemd units in tests
cat > "$GLOBAL_ENV" <<'EOF'
# Global env for integration tests
MARIADB_HOST=localhost
MARIADB_PORT=3306
CHROMADB_HOST=localhost
CHROMADB_PORT=3307
GRAFANA_PORT=3000
MCP_BUS_URL=http://localhost:8000
EOF

# Create a conda shim to simulate 'conda run --name env uvicorn ...' starting a tiny HTTP server
cat > "$CONDA_SHIM" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1" != "run" ]; then
  exec /usr/bin/env "$@"
fi
shift
if [ "$1" = "--name" ]; then
  shift 2
fi
cmd="$1"; shift
if [ "$cmd" = "uvicorn" ]; then
  port=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --port)
        port="$2"; shift 2;;
      --host)
        shift 2;;
      *)
        shift;;
    esac
  done
  if [ "$port" = "0" ]; then
    echo "No port specified" >&2; exit 1
  fi
  python3 - <<PYCODE &
import http.server, socketserver, sys
from urllib.parse import urlparse
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/health', '/ready', '/api/health'):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/shutdown':
            self.send_response(200)
            self.end_headers()
            sys.stdout.flush()
            import threading, time
            threading.Thread(target=lambda: (time.sleep(0.5), sys.exit(0))).start()
        else:
            self.send_response(404)
            self.end_headers()
Handler.protocol_version = 'HTTP/1.1'
with socketserver.TCPServer(("", int($port)), Handler) as httpd:
  print('Fake uvicorn server listening on', $port)
  httpd.serve_forever()
PYCODE
  disown -h %1
  exit 0
fi
exec /usr/bin/env "$cmd" "$@"
EOF
chmod +x "$CONDA_SHIM"

# Prepare PATH and override manifest
export PATH="$TMPDIR:$PATH"
export MANIFEST_OVERRIDE="$MANIFEST_FILE"
export GLOBAL_ENV_FILE="$GLOBAL_ENV"
export CANONICAL_ENV="justnews-py312"

# Run start script in no-detach mode
echo 'Starting mini stack (mcp_bus + test_agent) in non-detach mode...'
"$REPO_ROOT/scripts/ops/start_services_daemon.sh" --no-detach --health-timeout 3 > "$LOG_DIR/start.log" 2>&1 &
START_PID=$!
# Wait until the start script is done (it exits in --no-detach)
wait $START_PID || true

# Run the boot smoke test against manifest and global.env
# Ensure boot_smoke_test reads our override manifest
export MANIFEST_OVERRIDE="$MANIFEST_FILE"
export SMOKE_TIMEOUT_SEC=2
export SMOKE_RETRIES=3

echo 'Running boot smoke test...'
"$REPO_ROOT/infrastructure/systemd/helpers/boot_smoke_test.sh" > "$LOG_DIR/boot_smoke.log" 2>&1 || true
cat "$LOG_DIR/boot_smoke.log"

# Stop services
echo 'Stopping services...'
MANIFEST_OVERRIDE="$MANIFEST_FILE" bash "$REPO_ROOT/scripts/ops/stop_services.sh" > "$LOG_DIR/stop.log" 2>&1 || true
cat "$LOG_DIR/stop.log"

# Evaluate results: look for PASS entries in boot_smoke.log
OK_COUNT=$(grep -c '\[boot-smoke\] OK' "$LOG_DIR/boot_smoke.log" || true)
if [ "$OK_COUNT" -ge 1 ]; then
  echo "Integration Smoke Test: PASS (OK_COUNT=$OK_COUNT)"
  exit 0
else
  echo "Integration Smoke Test: FAIL — boot_smoke log details:" >&2
  sed -n '1,200p' "$LOG_DIR/boot_smoke.log" >&2
  exit 1
fi
