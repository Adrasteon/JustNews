#!/usr/bin/env bash
# Simple DB reachability check using JUSTNEWS_DB_URL from /etc/justnews/global.env
set -euo pipefail
GLOBAL_ENV="/etc/justnews/global.env"
if [[ -f "$GLOBAL_ENV" ]]; then
  # shellcheck disable=SC1090
  . "$GLOBAL_ENV"
fi
DB_URL="${JUSTNEWS_DB_URL:-${DATABASE_URL:-}}"
if [[ -z "$DB_URL" ]]; then
  echo "No DB URL found (JUSTNEWS_DB_URL or DATABASE_URL) in $GLOBAL_ENV" >&2
  exit 2
fi
# Prefer psql if available and URL is postgres
if command -v psql >/dev/null 2>&1 && [[ "$DB_URL" =~ ^postgres ]]; then
  PGPASSWORD="$(echo "$DB_URL" | sed -n 's#^postgresql\?://\([^:]*\):\([^@]*\)@.*#\2#p')" \
  psql "$DB_URL" -c 'SELECT 1;' -t -A -v ON_ERROR_STOP=1 >/dev/null && { echo "DB OK"; exit 0; } || { echo "DB FAIL"; exit 1; }
fi
# Fallback: attempt HTTP health on memory service
if curl -fsS --max-time 5 http://127.0.0.1:8007/health >/dev/null; then
  echo "DB proxy via Memory service appears healthy"; exit 0
fi
echo "DB check inconclusive (no psql; memory health failed)" >&2
exit 1
