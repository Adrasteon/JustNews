#!/usr/bin/env bash
# Apply synthesis migrations 004 and 005 with basic safety checks
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
MIGRATIONS=("$REPO_ROOT/database/migrations/004_add_synthesis_fields.sql" "$REPO_ROOT/database/migrations/005_create_synthesized_articles_table.sql")
LOG_DIR="$REPO_ROOT/logs/operations/migrations"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: apply_synthesis_migration.sh [DB_URL]"
  exit 0
fi

DB_URL="${1:-${JUSTNEWS_DB_URL:-}}"
if [[ -z "$DB_URL" ]]; then
  echo "Error: DB URL not provided. Set JUSTNEWS_DB_URL or pass it as first arg." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

for MIGRATION in "${MIGRATIONS[@]}"; do
  if [[ ! -f "$MIGRATION" ]]; then
    echo "Migration not found: $MIGRATION" >&2
    exit 1
  fi
  timestamp=$(date -u +"%Y%m%dT%H%M%SZ")
  echo "Applying $MIGRATION"
  if [[ "$DB_URL" =~ ^mysql:|^mariadb: ]]; then
    MYSQL_USER=$(echo "$DB_URL" | sed -E 's#.*//([^:]+):.*@.*#\1#')
    MYSQL_PASS=$(echo "$DB_URL" | sed -E 's#.*//[^:]+:([^@]+)@.*#\1#')
    MYSQL_HOST=$(echo "$DB_URL" | sed -E 's#.*@([^:/]+).*#\1#')
    MYSQL_PORT=$(echo "$DB_URL" | sed -E 's#.*:([0-9]+)/.*#\1#' )
    MYSQL_DBNAME=$(echo "$DB_URL" | sed -E 's#.*/([^/]+)$#\1#' )
    MYSQL_PORT=${MYSQL_PORT:-3306}
    MYSQL_PWD="$MYSQL_PASS" mysql --user="$MYSQL_USER" --host="$MYSQL_HOST" --port="$MYSQL_PORT" "$MYSQL_DBNAME" < "$MIGRATION" | tee "$LOG_DIR/migration_${timestamp}.log"
  else
    PAGER=cat psql "$DB_URL" -v ON_ERROR_STOP=1 -1 -f "$MIGRATION" | tee "$LOG_DIR/migration_${timestamp}.log"
  fi
done

echo "All migrations applied."