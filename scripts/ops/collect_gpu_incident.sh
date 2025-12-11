#!/usr/bin/env bash
# Collect GPU incident diagnostics into a directory for analysis
set -euo pipefail
OUT_DIR=${1:-/tmp/justnews_gpu_incident_$(date +%s)}
mkdir -p "$OUT_DIR"

echo "Collecting GPU incident artifacts into $OUT_DIR"

# NVML Watchdog logs
if [ -f /tmp/justnews_perf/nvml_watchdog.jsonl ]; then
    cp /tmp/justnews_perf/nvml_watchdog.jsonl "$OUT_DIR/"
fi

# GPU events logs
if [ -f logs/gpu_events.jsonl ]; then
    cp logs/gpu_events.jsonl "$OUT_DIR/"
fi

# nvidia-smi full state
nvidia-smi -q -x > "$OUT_DIR/nvidia_smi_full_$(date +%s).xml" 2>/dev/null || true

# dmesg tail
dmesg -T | tail -n 500 > "$OUT_DIR/dmesg_tail_$(date +%s).log" || true

# journalctl for justnews services (last 10 minutes)
journalctl -u justnews@* --since "10 minutes ago" > "$OUT_DIR/justnews_journal_$(date +%s).log" || true

# system logs
cp /var/log/syslog "$OUT_DIR/" 2>/dev/null || true
cp /var/log/kern.log "$OUT_DIR/" 2>/dev/null || true

# core dumps and coredumpctl info
coredumpctl list > "$OUT_DIR/coredumpctl_list_$(date +%s).txt" 2>/dev/null || true

# ls /proc/ PID info for processes that used GPU (approx from nvidia-smi running process list)
# Attempt to find PIDs from last nvml watchdog "running_procs"
if [ -f /tmp/justnews_perf/nvml_watchdog.jsonl ]; then
    # Extract PIDs using simple grep/jq if available; fallback to grep
    if command -v jq >/dev/null 2>&1; then
        jq -r 'select(.event == "nvml_sample") | .gpus[].running_procs[]?.pid' /tmp/justnews_perf/nvml_watchdog.jsonl | sort -u > "$OUT_DIR/gpu_procs_pids_$(date +%s).txt" || true
    else
        grep -o '"pid": [0-9]\+' /tmp/justnews_perf/nvml_watchdog.jsonl | sed 's/"pid": //' | sort -u > "$OUT_DIR/gpu_procs_pids_$(date +%s).txt" || true
    fi
fi

# Save environment
env > "$OUT_DIR/env_$(date +%s).txt"

# Pack up the collection
tar -czf "$OUT_DIR.tar.gz" -C "$(dirname $OUT_DIR)" "$(basename $OUT_DIR)" || true

echo "Collected GPU incident artifacts to: $OUT_DIR and $OUT_DIR.tar.gz"
