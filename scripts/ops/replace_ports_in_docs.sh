#!/usr/bin/env bash
# replace_ports_in_docs.sh — Replace common hard-coded service ports in docs/configs
# Usage: scripts/ops/replace_ports_in_docs.sh [--apply]
# Without --apply, it prints planned changes; with --apply it performs in-place edits.

set -euo pipefail
DRY_RUN=1
FOUND_CHANGES=0
if [[ "${1:-}" == "--apply" ]]; then
  DRY_RUN=0
fi

# Files to process (docs and JSON configs)
FILES=(
  COMPREHENSIVE_SYSTEMD_GUIDE.md
  monitoring/README.md
  agents/dashboard/config.json
  dashboard_config.json
  infrastructure/systemd/COMPREHENSIVE_SYSTEMD_GUIDE.md
)

# Replacements: PATTERN -> REPLACEMENT
# We use a small set of known ports and replace URLs or port-only occurrences with placeholders
GRAFANA_PLACE='${GRAFANA_PORT}'
PROMETHEUS_PLACE='${PROMETHEUS_PORT}'
MCP_BUS_PLACE='${MCP_BUS_URL}'
MARIADB_PLACE='${MARIADB_PORT}'
CHROMADB_PLACE='${CHROMADB_PORT}'
CRAWL4AI_PLACE='${CRAWL4AI_PORT}'
NODE_EXPORTER_PLACE='${NODE_EXPORTER_PORT}'
DCGM_EXPORTER_PLACE='${DCGM_EXPORTER_PORT}'

REPLACEMENTS=(
  "http://127.0.0.1:3000|http://127.0.0.1:${GRAFANA_PLACE}"
  "http://localhost:3000|http://localhost:${GRAFANA_PLACE}"
  "http://127.0.0.1:9090|http://127.0.0.1:${PROMETHEUS_PLACE}"
  "http://localhost:8000|${MCP_BUS_PLACE}"
  "localhost:8000|${MCP_BUS_PLACE}"
  "127.0.0.1:8000|${MCP_BUS_PLACE}"
  "3306|${MARIADB_PLACE}"
  "3307|${CHROMADB_PLACE}"
  "3308|${CRAWL4AI_PLACE}"
  "9100|${NODE_EXPORTER_PLACE}"
  "9400|${DCGM_EXPORTER_PLACE}"
)

for f in "${FILES[@]}"; do
  if [[ -f "$f" ]]; then
    echo "Processing $f"
    for r in "${REPLACEMENTS[@]}"; do
      IFS='|' read -r pat repl <<< "$r"
      if [[ "$DRY_RUN" -eq 1 ]]; then
        if grep -qF "$pat" "$f"; then
          echo "  would replace '$pat' -> '$repl' in $f"
          FOUND_CHANGES=1
        fi
      else
        if [ ! -w "$f" ]; then
          echo "  skipping $f (not writable by current user)"
          continue
        fi
        # Backup file first
        cp -v "$f" "$f.bak" || true
        # Use sed with '|' delimiter to avoid delimiter collision for URLs
        sed -i "s|$pat|$repl|g" "$f" || true
      fi
    done
  fi
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry-run complete. Re-run with --apply to perform replacements (files backed up with .bak)"
  if [[ "$FOUND_CHANGES" -eq 1 ]]; then
    echo "CHANGES_FOUND=true"
    exit 2
  fi
else
  echo "Replacements applied; backups saved with .bak suffix"
fi
