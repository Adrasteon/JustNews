#!/usr/bin/env bash
set -eo pipefail

# stress_gpu_harness.sh - start NVML watchdog, run a stress workload, and collect artifacts

WATCHDOG_LOG_DIR=${WATCHDOG_LOG_DIR:-/tmp/justnews_perf}
OUTPUT_DIR=${OUTPUT_DIR:-/tmp/justnews_perf/output}
mkdir -p "${WATCHDOG_LOG_DIR}" "${OUTPUT_DIR}"

echo "Activating conda env justnews-py312"
source ~/miniconda3/etc/profile.d/conda.sh
conda activate justnews-py312

echo "Starting NVML watchdog"
python scripts/perf/nvml_dropout_watchdog.py --log-file "${WATCHDOG_LOG_DIR}/nvml_watchdog.jsonl" --interval 1.0 --context-samples 240 --capture-dmesg --dmesg-lines 200 &
WATCHDOG_PID=$!
echo "NVML watchdog PID=${WATCHDOG_PID}"

sleep 2

echo "Starting GPU stress run"
RE_RANKER_TEST_MODE=${RE_RANKER_TEST_MODE:-0}
RE_RANKER_MODEL=${RE_RANKER_MODEL:-mistralai/Mistral-7B-Instruct}
WORKERS=${WORKERS:-6}
REQUESTS=${REQUESTS:-100}

python scripts/perf/simulate_concurrent_inference.py --workers ${WORKERS} --requests ${REQUESTS} --model "${RE_RANKER_MODEL}" --repeat 1

echo "Stress run complete; collecting artifacts"
pgrep -f nvml_dropout_watchdog || true
cp "${WATCHDOG_LOG_DIR}/nvml_watchdog.jsonl" "${OUTPUT_DIR}/nvml_watchdog.$(date +%s).jsonl"
python -c "import json,sys; a=open('${WATCHDOG_LOG_DIR}/nvml_watchdog.jsonl').read().strip().splitlines()[-20:]; print('\n'.join(a))" > "${OUTPUT_DIR}/nvml_tail.jsonl" || true

echo "nvidia-smi snapshot"
nvidia-smi -q > "${OUTPUT_DIR}/nvidia_smi.$(date +%s).txt" || true

echo "Collecting journalctl logs for justnews services"
journalctl -u justnews@* -n 500 > "${OUTPUT_DIR}/justnews_journal.$(date +%s).log" || true

echo "Done. Kill watchdog PID ${WATCHDOG_PID}"
kill ${WATCHDOG_PID} || true
exit 0
