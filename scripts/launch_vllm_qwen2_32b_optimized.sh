#!/usr/bin/env bash
# Launch vLLM server for Qwen2-32B-Instruct AWQ with ALL optimizations
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

# vLLM configuration with optimizations
VLLM_MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-14B-Instruct-AWQ}"
VLLM_PORT="${VLLM_PORT:-7060}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-4096}"  # Safe for 14B on 24GB
VLLM_GPU_MEMORY_UTIL="${VLLM_GPU_MEMORY_UTIL:-0.90}"  # Higher with FP8 KV cache
VLLM_QUANTIZATION="${VLLM_QUANTIZATION:-awq}"

# KV Cache data type - auto will use best default for model
VLLM_KV_CACHE_DTYPE="${VLLM_KV_CACHE_DTYPE:-auto}"  # auto selects best (bfloat16 or float16)

# Chunked Prefill Optimization
VLLM_MAX_NUM_BATCHED_TOKENS="${VLLM_MAX_NUM_BATCHED_TOKENS:-8192}"

# Continuous Batching Tuning
VLLM_MAX_NUM_SEQS="${VLLM_MAX_NUM_SEQS:-64}"  # Tune based on agent concurrency

# Multi-LoRA Support
VLLM_ENABLE_LORA="${VLLM_ENABLE_LORA:-false}"
VLLM_MAX_LORAS="${VLLM_MAX_LORAS:-8}"
VLLM_MAX_LORA_RANK="${VLLM_MAX_LORA_RANK:-64}"
VLLM_LORA_MODULES="${VLLM_LORA_MODULES:-}"

# Prefix Caching (enabled by default in v1, but explicit)
VLLM_ENABLE_PREFIX_CACHING="${VLLM_ENABLE_PREFIX_CACHING:-true}"

# Compilation optimization (disable if causing issues)
VLLM_DISABLE_COMPILE="${VLLM_DISABLE_COMPILE:-true}"  # Disabled to save memory

echo "===== vLLM Qwen2-14B Optimized Launcher ====="
echo "Model: $VLLM_MODEL"
echo "Port: $VLLM_PORT"
echo "Host: $VLLM_HOST"
echo "Max model length: $VLLM_MAX_MODEL_LEN"
echo "GPU memory utilization: $VLLM_GPU_MEMORY_UTIL"
echo "Quantization: $VLLM_QUANTIZATION"
echo "KV Cache dtype: $VLLM_KV_CACHE_DTYPE (FP8 = 50% memory savings!)"
echo "Max batched tokens: $VLLM_MAX_NUM_BATCHED_TOKENS"
echo "Max sequences: $VLLM_MAX_NUM_SEQS"
echo "Prefix caching: $VLLM_ENABLE_PREFIX_CACHING"
echo "LoRA enabled: $VLLM_ENABLE_LORA"
if [[ "$VLLM_ENABLE_LORA" == "true" ]]; then
    echo "Max LoRAs: $VLLM_MAX_LORAS"
    echo "Max LoRA rank: $VLLM_MAX_LORA_RANK"
fi
echo "===================================================="

# Activate conda environment
if [[ -n "${CONDA_PREFIX:-}" ]] && [[ "$CONDA_PREFIX" == *"justnews-py312"* ]]; then
    echo "Already in justnews-py312 environment."
else
    echo "Activating conda environment: justnews-py312"
    eval "$(conda shell.bash hook)"
    conda activate justnews-py312
fi

# Check vLLM is installed
if ! python -c "import vllm" 2>/dev/null; then
    echo "ERROR: vLLM not installed. Install with:"
    echo "  pip install vllm"
    exit 1
fi

# Build vLLM command with ALL optimizations
VLLM_CMD=(
    python -m vllm.entrypoints.openai.api_server
    --model "$VLLM_MODEL"
    --host "$VLLM_HOST"
    --port "$VLLM_PORT"
    --quantization "$VLLM_QUANTIZATION"
    --max-model-len "$VLLM_MAX_MODEL_LEN"
    --gpu-memory-utilization "$VLLM_GPU_MEMORY_UTIL"
    
    # FP8 KV Cache - CRITICAL for 32B on 24GB!
    --kv-cache-dtype "$VLLM_KV_CACHE_DTYPE"
    
    # Chunked Prefill Optimization
    --max-num-batched-tokens "$VLLM_MAX_NUM_BATCHED_TOKENS"
    
    # Continuous Batching
    --max-num-seqs "$VLLM_MAX_NUM_SEQS"
    
    # Prefix Caching (explicit enable)
    --enable-prefix-caching
    
    # Other optimizations
    --disable-log-requests
    --trust-remote-code
)

# Add LoRA support if enabled
if [[ "$VLLM_ENABLE_LORA" == "true" ]]; then
    VLLM_CMD+=(
        --enable-lora
        --max-loras "$VLLM_MAX_LORAS"
        --max-lora-rank "$VLLM_MAX_LORA_RANK"
    )
    if [[ -n "$VLLM_LORA_MODULES" ]]; then
        VLLM_CMD+=(--lora-modules "$VLLM_LORA_MODULES")
    fi
fi

# torch.compile is enabled by default in vLLM 0.12.0, no flag to disable it
# Memory savings will come from FP8 KV cache instead

# Export HF_TOKEN if available
if [[ -n "${HF_TOKEN:-}" ]]; then
    export HF_TOKEN
    echo "HF_TOKEN: set (masked)"
else
    echo "WARNING: HF_TOKEN not set; gated model access may fail."
fi

# Set CUDA library paths for FlashInfer JIT compilation
export CUDA_HOME="${CONDA_PREFIX}"
export CUDA_PATH="${CONDA_PREFIX}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${CONDA_PREFIX}/lib64:${CONDA_PREFIX}/targets/x86_64-linux/lib:${LD_LIBRARY_PATH:-}"
export LIBRARY_PATH="${CONDA_PREFIX}/lib:${CONDA_PREFIX}/lib64:${CONDA_PREFIX}/targets/x86_64-linux/lib:${LIBRARY_PATH:-}"
# Reduce optimization to avoid GCC internal compiler errors with FP8 kernels
export CXXFLAGS="-O1"  # Reduce from -O3 to -O1 to avoid GCC segfault
export NVCC_PREPEND_FLAGS="-O1"  # Override FlashInfer's -O3
echo "CUDA_HOME: $CUDA_HOME"
echo "CXXFLAGS: $CXXFLAGS (reduced optimization to avoid GCC crash)"
echo "LD_LIBRARY_PATH configured for FlashInfer compilation"

# Launch vLLM
echo ""
echo "Launching vLLM server with optimizations..."
echo "Command: ${VLLM_CMD[*]}"
echo ""
exec "${VLLM_CMD[@]}"
