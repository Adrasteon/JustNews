#!/usr/bin/env bash
# Simple GPU + memory monitor that appends sampling data to a log file
# Usage: scripts/gpu_monitor.sh /tmp/gpu_monitor.log [interval_seconds]
set -euo pipefail

LOG=${1:-/tmp/gpu_monitor.log}
INTERVAL=${2:-1}

echo "Starting GPU monitor: logging to $LOG (interval=${INTERVAL}s)"

while true; do
  date --iso-8601=seconds >> "$LOG"
  echo "--- nvidia-smi compute-apps ---" >> "$LOG"
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv >> "$LOG" 2>&1 || true
  echo "--- nvidia-smi summary ---" >> "$LOG"
  nvidia-smi -q -d MEMORY,TEMPERATURE,POWER >> "$LOG" 2>&1 || true
  echo "--- free -h ---" >> "$LOG"
  free -h >> "$LOG" 2>&1 || true
  echo "--- top RSS (top 20) ---" >> "$LOG"
  ps aux --sort=-rss | head -n 20 >> "$LOG" 2>&1 || true
  echo "----" >> "$LOG"
  sleep "$INTERVAL"
done
