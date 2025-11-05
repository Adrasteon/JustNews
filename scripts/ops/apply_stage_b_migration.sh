#!/usr/bin/env bash
# Apply Stage B migration 003 with safety checks and optional evidence capture
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
MIGRATION_FILE="$REPO_ROOT/database/migrations/003_stage_b_ingestion.sql"
EVIDENCE_LOG="$REPO_ROOT/docs/operations/stage_b_validation_evidence_log.md"
LOG_DIR="$REPO_ROOT/logs/operations/migrations"

print_usage() {
  cat <<'USAGE'
Usage: apply_stage_b_migration.sh [DB_URL] [--record]

Arguments:
  DB_URL    Optional Postgres connection string. Falls back to JUSTNEWS_DB_URL.
  --record  Append a timestamped note to the Stage B evidence log on success.

Environment:
  JUSTNEWS_DB_URL  Default connection string if DB_URL not provided.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  print_usage
  exit 0
fi

DB_URL="${1:-}"
RECORD_FLAG="${2:-}"

if [[ -z "$DB_URL" ]]; then
  DB_URL="${JUSTNEWS_DB_URL:-}"
fi

if [[ -z "$DB_URL" ]]; then
  echo "Error: database URL not provided. Set JUSTNEWS_DB_URL or pass it as the first argument." >&2
  exit 1
fi

if [[ ! -f "$MIGRATION_FILE" ]]; then
  echo "Error: migration file not found at $MIGRATION_FILE" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
log_file="$LOG_DIR/migration_003_${timestamp}.log"

echo "Applying migration 003_stage_b_ingestion using $MIGRATION_FILE"
echo "Logging output to $log_file"
PAGER=cat psql "$DB_URL" -v ON_ERROR_STOP=1 -1 -f "$MIGRATION_FILE" | tee "$log_file"

echo "Migration applied successfully."

if [[ "$RECORD_FLAG" == "--record" ]]; then
  if [[ ! -f "$EVIDENCE_LOG" ]]; then
    echo "Warning: evidence log not found at $EVIDENCE_LOG" >&2
    exit 0
  fi
  timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  {
    echo "- ${timestamp} — Migration 003 applied via scripts/ops/apply_stage_b_migration.sh"
  } >> "$EVIDENCE_LOG"
  echo "Recorded migration evidence entry in $EVIDENCE_LOG"
fi
