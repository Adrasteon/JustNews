#!/usr/bin/env bash
# Launch vLLM server for Mistral-7B-Instruct-v0.3 with per-agent LoRA adapters
# Port: 7060 (separate from agent services 8000-8030)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load global env for HF_TOKEN, MODEL_STORE_ROOT, etc.
if [[ -f "$REPO_ROOT/global.env" ]]; then
    set -a
    source "$REPO_ROOT/global.env"
    set +a
fi

# vLLM configuration
VLLM_MODEL="${VLLM_MODEL:-mistralai/Mistral-7B-Instruct-v0.3}"
VLLM_PORT="${VLLM_PORT:-7060}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-4096}"
VLLM_GPU_MEMORY_UTIL="${VLLM_GPU_MEMORY_UTIL:-0.75}"
VLLM_QUANTIZATION="${VLLM_QUANTIZATION:-}"

# LoRA adapter support (temporarily disabled to ensure clean startup)
VLLM_ENABLE_LORA="false"
VLLM_LORA_MODULES=""

echo "===== vLLM Mistral-7B-Instruct Launcher with LoRA ====="
echo "Model: $VLLM_MODEL"
echo "Port: $VLLM_PORT"
echo "Host: $VLLM_HOST"
echo "Max model length: $VLLM_MAX_MODEL_LEN"
echo "GPU memory utilization: $VLLM_GPU_MEMORY_UTIL"
echo "Quantization: ${VLLM_QUANTIZATION:-none (fp16)}"
echo "LoRA enabled: $VLLM_ENABLE_LORA"
echo "LoRA modules: ${VLLM_LORA_MODULES:-(none configured)}"
echo "==================================================="

# Activate conda environment
if [[ -n "${CONDA_PREFIX:-}" ]] && [[ "$CONDA_PREFIX" == *"${CANONICAL_ENV:-justnews-py312}"* ]]; then
    echo "Already in ${CANONICAL_ENV:-justnews-py312} environment."
else
    echo "Activating conda environment: ${CANONICAL_ENV:-justnews-py312}"
    eval "$(conda shell.bash hook)"
    conda activate "${CANONICAL_ENV:-justnews-py312}"
fi

# Check vLLM is installed
if ! python -c "import vllm" 2>/dev/null; then
    echo "ERROR: vLLM not installed. Install with:"
    echo "  pip install vllm"
    exit 1
fi

# Build vLLM command
VLLM_CMD=(
    python -m vllm.entrypoints.openai.api_server
    --model "$VLLM_MODEL"
    --host "$VLLM_HOST"
    --port "$VLLM_PORT"
    --max-model-len "$VLLM_MAX_MODEL_LEN"
    --gpu-memory-utilization "$VLLM_GPU_MEMORY_UTIL"
    --disable-log-requests
    --trust-remote-code
)

# Add quantization if specified
if [[ -n "$VLLM_QUANTIZATION" ]]; then
    VLLM_CMD+=(--quantization "$VLLM_QUANTIZATION")
fi

# Add LoRA support if enabled
if [[ "$VLLM_ENABLE_LORA" == "true" ]] && [[ -n "$VLLM_LORA_MODULES" ]]; then
    VLLM_CMD+=(--enable-lora --lora-modules "$VLLM_LORA_MODULES")
fi

# Export HF_TOKEN if available
if [[ -n "${HF_TOKEN:-}" ]]; then
    export HF_TOKEN
    echo "HF_TOKEN: set (masked)"
else
    echo "WARNING: HF_TOKEN not set; gated model access may fail."
fi

# Launch vLLM
echo "Launching vLLM server..."
exec "${VLLM_CMD[@]}"
