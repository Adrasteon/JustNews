#!/bin/bash
# GPU Stress Test Harness for Mistral-7B INT8
# Tests real model loading with NVML monitoring and power cap enforcement
# 
# Usage: ./stress_test_harness.sh [stub|real] [workers] [requests]
#   ./stress_test_harness.sh stub 4 40    # Fast stub test
#   ./stress_test_harness.sh real 2 10    # Real model test (slow)
#
# Tests are logged to /home/adra/justnews_gpu_logs/

set -e

TEST_MODE="${1:-stub}"
WORKERS="${2:-4}"
REQUESTS="${3:-40}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="/home/adra/justnews_gpu_logs"
CONDA_ENV="/home/adra/miniconda3/envs/justnews-py312"
CONDA_CMD="/home/adra/miniconda3/bin/conda run -p $CONDA_ENV --no-capture-output"

# Create log directory
mkdir -p "$LOG_DIR"

# Verify power cap
echo "[INFO] Verifying 300W power cap..."
POWER_LIMIT=$(sudo nvidia-smi -q -d POWER | grep "Current Power Limit" | head -1 | awk '{print $4}')
if [ "$POWER_LIMIT" != "300.00" ]; then
    echo "[WARN] Power limit not 300W, applying..."
    sudo nvidia-smi -pl 300 || echo "[WARN] Failed to set power limit"
fi
echo "[INFO] Power limit: $POWER_LIMIT W"

# Verify GPU health
echo "[INFO] Checking GPU health..."
nvidia-smi --query-gpu=name,temperature.gpu,power.draw,memory.used --format=csv,noheader,nounits

# Set test mode
if [ "$TEST_MODE" = "real" ]; then
    export RE_RANKER_TEST_MODE=0
    export RE_RANKER_MODEL="mistralai/Mistral-7B-Instruct-v0.3"
    TEST_NAME="mistral_real_${WORKERS}w_${TIMESTAMP}"
    echo "[INFO] Running REAL model test (slow, will download/load model)"
else
    export RE_RANKER_TEST_MODE=1
    TEST_NAME="mistral_stub_${WORKERS}w_${TIMESTAMP}"
    echo "[INFO] Running STUB model test (fast, no model loading)"
fi

# Start NVML watchdog
echo "[INFO] Starting NVML watchdog..."
WATCHDOG_LOG="$LOG_DIR/nvml_watchdog_${TEST_NAME}.jsonl"
WATCHDOG_STDOUT="$LOG_DIR/nvml_watchdog_${TEST_NAME}.stdout.log"
$CONDA_CMD python scripts/perf/nvml_dropout_watchdog.py \
    --interval 0.1 --context-samples 400 \
    --log-file "$WATCHDOG_LOG" \
    --emit-samples --capture-dmesg --dmesg-lines 50 \
    > "$WATCHDOG_STDOUT" 2>&1 &
WATCHDOG_PID=$!
echo "[INFO] Watchdog PID: $WATCHDOG_PID"
sleep 2

# Run test
TEST_LOG="$LOG_DIR/${TEST_NAME}.log"
echo "[INFO] Starting stress test: $WORKERS workers, $REQUESTS requests"
echo "[INFO] Test output: $TEST_LOG"
$CONDA_CMD python scripts/perf/simulate_concurrent_inference.py \
    --workers "$WORKERS" \
    --requests "$REQUESTS" \
    --model mistralai/Mistral-7B-Instruct-v0.3 \
    > "$TEST_LOG" 2>&1
TEST_EXIT=$?

# Stop watchdog
sleep 2
kill $WATCHDOG_PID 2>/dev/null || true
wait $WATCHDOG_PID 2>/dev/null || true

# Report results
echo ""
echo "==============================================="
echo "TEST RESULTS"
echo "==============================================="
echo "Mode:        $TEST_MODE"
echo "Workers:     $WORKERS"
echo "Requests:    $REQUESTS"
echo "Exit Code:   $TEST_EXIT"
echo "Test Log:    $TEST_LOG"
echo "Watchdog:    $WATCHDOG_LOG"
echo ""
echo "--- Test Output ---"
cat "$TEST_LOG"
echo ""
echo "--- GPU State ---"
nvidia-smi
echo ""
echo "--- Watchdog Telemetry ---"
if [ -f "$WATCHDOG_LOG" ]; then
    SAMPLE_COUNT=$(grep -c "nvml_sample" "$WATCHDOG_LOG" || echo "0")
    EXCEPTION_COUNT=$(grep -c "nvml_exception" "$WATCHDOG_LOG" || echo "0")
    echo "NVML Samples:   $SAMPLE_COUNT"
    echo "NVML Exceptions: $EXCEPTION_COUNT"
    
    if [ "$SAMPLE_COUNT" -gt 0 ]; then
        echo ""
        grep nvml_sample "$WATCHDOG_LOG" | jq '.gpus[0] | {power: .power_w, temp: .temperature_c, util: .utilization_gpu_pct, mem: .memory_used_mb}' 2>/dev/null | \
        jq -s 'reduce .[] as $item ({}; .power_w += [$item.power] | .temp_c += [$item.temp] | .util += [$item.util] | .mem_mb += [$item.mem]) | 
                {power_w: (.power_w | {min: min | floor, max: max | floor, avg: (add/length | round)}), 
                 temp_c: (.temp_c | {min: min, max: max, avg: (add/length | round)}), 
                 util: (.util | {min: min, max: max}), 
                 mem_mb: (.mem_mb | {min: (min | floor), max: (max | floor), avg: (add/length | floor)})}' 2>/dev/null || echo "(stats unavailable)"
    fi
fi

exit $TEST_EXIT
