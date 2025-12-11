#!/usr/bin/env bash
# Orchestrated stress runner for full E2E flows (intended for an isolated staging host)
# WARNING: this will exercise models, DBs, browsers and may saturate host resources.
# Only run on a dedicated, contained machine or container with monitoring and artifact collection.

set -euo pipefail

DURATION=${1:-600}       # total run time in seconds (default: 10 minutes)
CONCURRENCY=${2:-3}      # how many parallel run_full_canary.py instances to spin
CRAWL_CONCURRENCY=${3:-2} # how many concurrent crawl_schedule runs
OUTPUT_DIR=output/stress_run
MONITOR_INTERVAL=2

mkdir -p ${OUTPUT_DIR}

# Default: run in 'live' mode (loading model weights). Set STAGING_DRY_RUN=1 to avoid heavy models.
STAGING_DRY_RUN=${STAGING_DRY_RUN:-0}

# 1) Start resource monitor
echo "Starting resource monitor (interval=${MONITOR_INTERVAL}s, duration=${DURATION}s) -> ${OUTPUT_DIR}/resource_trace.jsonl"
python3 scripts/dev/resource_monitor.py --output ${OUTPUT_DIR}/resource_trace.jsonl --interval ${MONITOR_INTERVAL} --duration ${DURATION} &
MON_PID=$!

echo "monitor pid=${MON_PID}"

# Helper to spawn background stress tasks
spawn_canary() {
  idx=$1
  LOG=${OUTPUT_DIR}/canary_${idx}.log
  if [ "${STAGING_DRY_RUN}" = "1" ]; then
    echo "(dry-run) spawn canary ${idx} -> ${LOG}"
    PYTHONPATH=$(pwd) MODEL_STORE_DRY_RUN=1 scripts/dev/run_full_canary.py > ${LOG} 2>&1 &
  else
    echo "spawn canary ${idx} -> ${LOG}"
    PYTHONPATH=$(pwd) scripts/dev/run_full_canary.py > ${LOG} 2>&1 &
  fi
  echo $! >> ${OUTPUT_DIR}/canary_pids.txt
}

# Spawn a few concurrent canary runs
for i in $(seq 1 ${CONCURRENCY}); do
  spawn_canary ${i}
  # small stagger
  sleep 2
done

# Spawn crawl stress tasks
for i in $(seq 1 ${CRAWL_CONCURRENCY}); do
  LOG=${OUTPUT_DIR}/crawl_${i}.log
  echo "spawn crawl ${i} -> ${LOG}"
  PYTHONPATH=$(pwd) LIVE_CONCURRENT_SITES=${CRAWL_CONCURRENCY} JUSTNEWS_TEST_MAX_ARTICLES_PER_SITE=10 python3 scripts/ops/run_crawl_schedule.py --profiles config/crawl_profiles --max-target 50 > ${LOG} 2>&1 &
  echo $! >> ${OUTPUT_DIR}/crawl_pids.txt
  sleep 1
done

# Optionally spawn editorial harness runs that may load Mistral adapters
for i in $(seq 1 ${CONCURRENCY}); do
  LOG=${OUTPUT_DIR}/harness_${i}.log
  if [ "${STAGING_DRY_RUN}" = "1" ]; then
    echo "(dry-run) harness ${i} -> ${LOG}"
    PYTHONPATH=$(pwd) MODEL_STORE_DRY_RUN=1 python3 scripts/dev/run_agent_chain_harness.py --dry-run --limit 5 > ${LOG} 2>&1 &
  else
    echo "harness ${i} -> ${LOG}"
    PYTHONPATH=$(pwd) python3 scripts/dev/run_agent_chain_harness.py --dry-run --limit 5 > ${LOG} 2>&1 &
  fi
  echo $! >> ${OUTPUT_DIR}/harness_pids.txt
  sleep 1
done

# Let the run proceed for DURATION seconds while monitor collects samples
echo "Stress run active — sleeping for ${DURATION}s"
sleep ${DURATION}

echo "Stress run complete — terminating background tasks and monitor"

if [ -s ${OUTPUT_DIR}/canary_pids.txt ]; then
  cat ${OUTPUT_DIR}/canary_pids.txt | xargs -r -n1 -I{} kill -TERM {} || true
fi
if [ -s ${OUTPUT_DIR}/crawl_pids.txt ]; then
  cat ${OUTPUT_DIR}/crawl_pids.txt | xargs -r -n1 -I{} kill -TERM {} || true
fi
if [ -s ${OUTPUT_DIR}/harness_pids.txt ]; then
  cat ${OUTPUT_DIR}/harness_pids.txt | xargs -r -n1 -I{} kill -TERM {} || true
fi

# Ensure monitor is stopped
if ps -p ${MON_PID} > /dev/null 2>&1; then
  kill -TERM ${MON_PID} || true
fi

# Give processes a moment then capture final state
sleep 3
ps aux | sort -nrk 4 | head -n 40 > ${OUTPUT_DIR}/ps_top.txt || true
nvidia-smi > ${OUTPUT_DIR}/nvidia_smi_end.txt || true

echo "Stress artifacts in ${OUTPUT_DIR}"
