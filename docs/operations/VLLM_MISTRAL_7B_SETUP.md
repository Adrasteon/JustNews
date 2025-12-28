# Mistral‑7B vLLM Integration Guide

> **Note:** Qwen2 experiments are retired; this guide now documents using the Mistral‑7B fallback as the default vLLM model. Historical Qwen2 notes are preserved further below for reference.

## Overview

> Note: The launcher now points to the stable fallback **Mistral-7B-Instruct-v0.3** on port **7060**. Qwen2-32B attempts are paused after hardware resets. This doc is retained for context but uses the new launcher name.

This guide covers the integration of a vLLM-served model on a 24GB RTX 3090. The current setup uses:

- **Base model**: Mistral-7B-Instruct-v0.3 (fp16/bf16) on port 7060.

- **Per-agent adapters**: (temporarily disabled) will be re-enabled when the LoRA module list is finalized.

## Quick Start

### 1. Install vLLM

```bash
conda activate justnews-py312
pip install vllm

```text

### 2. Launch vLLM Server

```bash

## Port 7060 (outside agent range)

./scripts/launch_vllm_mistral_7b.sh

```text

The script reads `global.env` for `HF_TOKEN` and launches vLLM with:

- Model: `mistralai/Mistral-7B-Instruct-v0.3`

- Quantization: none (fp16/bf16)

- Max model length: 4096 tokens

- GPU memory utilization: 0.75

- Port: 7060

### 3. Run Smoke Test

```bash
conda activate justnews-py312
python tests/integration/test_vllm_mistral_7b_smoke.py

```text

Expected output:

```text
Testing health endpoint: <http://127.0.0.1:7060/v1/health>
✅ Health check passed
Testing models endpoint: <http://127.0.0.1:7060/v1/models>
✅ Models: ['mistralai/Mistral-7B-Instruct-v0.3']
Testing chat completion: <http://127.0.0.1:7060/v1/chat/completions>
✅ Chat completion result: 4

✅ All tests passed!

```text

### 4. Enable vLLM for Agents

Set `VLLM_ENABLED=true` in `global.env`:

```bash

## In global.env

VLLM_ENABLED=true

```text

Agents will now route inference to the vLLM endpoint (`<http://127.0.0.1:7060/v1>`) instead of local transformers.

## Configuration

### Environment Variables

Key variables in `global.env`:

```bash

## vLLM Mistral-7B Inference Endpoint

VLLM_ENABLED=false           # Set to true to enable
VLLM_BASE_URL=<http://127.0.0.1:7060/v1>
VLLM_API_KEY=dummy           # vLLM doesn't require auth
VLLM_MODEL=mistralai/Mistral-7B-Instruct-v0.3
VLLM_PORT=7060

```text

### vLLM Config File

`config/legacy/vllm_qwen2_32b.yaml` (ARCHIVED) contains historical Qwen2 settings. The authoritative, current
configuration is `config/vllm_mistral_7b.yaml` which should be used for production.

- Endpoint settings (host, port, base URL)

- Per-agent adapter names (for vLLM LoRA hot-swap)

- Training settings (QLoRA parameters for 24GB 3090, when training Mistral adapters)

- Fallback config (Mistral-7B + adapters) - use `config/vllm_mistral_7b.yaml` for runtime fallbacks


### Local dev: starting vLLM and running smoke tests

### Tests & Validation (developer)

- **Smoke tests**: The vLLM smoke test is `tests/integration/test_vllm_mistral_7b_smoke.py` and validates the `/health`, `/models`, and `/chat/completions` responses for basic functionality.

- **Orchestrator tests**: See `tests/agents/gpu_orchestrator/test_model_lifecycle.py` to validate ModelSpec resolution, adapter path extraction from `AGENT_MODEL_MAP.json`, and OOM/restart handling.

- **Run tests locally** (canonical env):

```bash
conda run -n justnews-py312 pytest -q tests/integration/test_vllm_mistral_7b_smoke.py -q
conda run -n justnews-py312 pytest -q tests/agents/gpu_orchestrator/test_model_lifecycle.py -q
```

- **Test best practices**:
  - For integration smoke tests, use `./scripts/wait_for_vllm.sh` to ensure the server is ready before running tests.
  - Use `VLLM_SKIP_START=1` and `CUDA_VISIBLE_DEVICES=""` for CI or environments without GPUs to avoid starting a GPU-heavy server.
  - Tests that need vLLM running should only be executed on a GPU-capable host (local dev or gated GPU CI).

## Ensure VLLM_BASE_URL is set in your env or /etc/justnews/global.env

For local development, start the vLLM server and wait for it to be ready before running the smoke tests.

Examples:

```bash
# start vLLM (from repo root) - conservative GPU usage
VLLM_QUANTIZATION= VLLM_GPU_MEMORY_UTIL=0.6 ./scripts/launch_vllm_mistral_7b.sh > run/vllm_mistral_fp16.log 2>&1 &

# wait for the server to be healthy (includes models endpoint check; accepts optional API key)
./scripts/wait_for_vllm.sh --base-url http://127.0.0.1:7060 --api-key "$VLLM_API_KEY" --timeout 30

# Run smoke tests (ensure VLLM_API_KEY is exported in the same shell)
export VLLM_API_KEY=REPLACE_WITH_YOUR_VLLM_API_KEY
./scripts/run_with_env.sh conda run -n ${CANONICAL_ENV:-justnews-py312} pytest -q tests/integration/test_vllm_mistral_7b_smoke.py -k chat_completion
```

Notes:

- CI runners typically do not have GPUs available; running the full vLLM server in CI is not recommended unless special GPU-enabled runners are provisioned. Instead, use the 'mistral-dryrun' job for adapter dry-run tests; the smoke test is intended for local dev or gated GPU CI.
- The smoke test now includes short retry/backoff logic for transient readiness/auth races and validates model responses more robustly.


### Agent Model Mappings

#### AGENT_MODEL_MAP.json

- **base_models**: Historical Qwen2 entries have been archived (see `config/legacy/vllm_qwen2_32b.yaml`).

- **vllm_agents**: The project now uses Mistral-7B by default; per-agent adapter mappings use `mistral_<agent>_v1` adapters and `inference_mode: "vllm"` routes to vLLM.

#### AGENT_MODEL_RECOMMENDED.json

Orchestrator-managed model deployments
--------------------------------------

We recommend deploying the canonical Mistral-7B model under control of the `gpu_orchestrator` agent. The orchestrator will read `config/vllm_mistral_7b.yaml` and attempt to start the model using the `service.systemd_unit` listed in the config; fallback to the local vLLM process is supported when systemd is not available.

Key operational steps:

- Place the systemd unit example in `infrastructure/systemd/vllm-mistral-7b.service.example` under `/etc/systemd/system/vllm-mistral-7b.service` and enable it:

```
sudo cp infrastructure/systemd/vllm-mistral-7b.service.example /etc/systemd/system/vllm-mistral-7b.service
sudo systemctl daemon-reload
sudo systemctl enable --now vllm-mistral-7b.service
```

- The `gpu_orchestrator` will collect adapters listed in `AGENT_MODEL_MAP.json` and expose `adapter_paths` on the `ModelSpec` for downstream adapter mounting (PEFT/LoRA) where supported by the runtime.

- Monitoring and safety: the orchestrator will only start the model when sufficient GPU headroom exists and will monitor logs for CUDA OOM. It exports metrics `gpu_orchestrator_vllm_restarts_total`, `gpu_orchestrator_vllm_ooms_total`, and `gpu_orchestrator_vllm_status`.


- Each agent now has:

  - `default`: mistralai/Mistral-7B-Instruct-v0.3 (fallback)

  - `vllm_default`: mistralai/Mistral-7B-Instruct-v0.3 (when `VLLM_ENABLED=true`)

- Comment at top documents the toggle and notes that legacy Qwen2 adapters are archived.

## Training Per-Agent Adapters

### QLoRA Training on 24GB 3090

Use `scripts/train_qlora.py` (recommended) to train Mistral adapters. Historical Qwen2 training scripts are archived at
`scripts/legacy/train_qwen2_qlora.py`.

```bash
conda activate justnews-py312

## Example: train synthesizer adapter (Mistral)

python scripts/train_qlora.py \
  --model_name_or_path mistralai/Mistral-7B-Instruct \
  --config_path config/vllm_mistral_7b.yaml \
  --train_file data/synth_finetune.jsonl \
  --agent_name synthesizer \
  --adapter_name mistral_synth_v1 \
  --output_dir output/adapters \
  --max_steps 1000 \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 16 \
  --learning_rate 2e-4 \
  --bf16 \
  --publish

```text

Key parameters (optimized for 24GB):

- **Quantization**: NF4 (4-bit)

- **LoRA rank**: 16 (alpha=32, dropout=0.05)

- **Batch size**: 1 + gradient accumulation 16

- **Optimizer**: `paged_adamw_8bit` (saves VRAM)

- **Gradient checkpointing**: enabled

- **Max seq length**: 2048 tokens

- **BF16**: enabled for faster compute

### Publish to ModelStore

Add `--publish` flag to copy trained adapter to `model_store/adapters/<agent>/<adapter_name>/`.

### Repeat for All Agents

Train adapters for all 8 agents:

- synthesizer

- re_ranker

- fact_checker

- critic

- journalist

- chief_editor

- reasoning

- analyst

## vLLM with LoRA Adapters

vLLM supports LoRA hot-swapping. To enable:

1. Set `VLLM_ENABLE_LORA=true` in launch script env.

1. Pass `VLLM_LORA_MODULES` as comma-separated `name=path` pairs:

```bash VLLM_LORA_MODULES="synthesizer=/home/adra/JustNews/model_store/adapters/
synthesizer/mistral_synth_v1,critic=/home/adra/JustNews/model_store/adapters/cri
tic/mistral_critic_v1" ```

1. Restart vLLM server with `./scripts/launch_vllm_mistral_7b.sh`.

Client code can request a specific adapter via the `model` field in the OpenAI
API call (if vLLM is configured to route by adapter name).

---

## Environment & Troubleshooting 🔧

Recommended canonical environment: `justnews-py312` (see `environment.yml`). Key
runtime requirements for vLLM Mistral-7B:

- Python: 3.12 (conda env `justnews-py312`) ✅

- PyTorch: **2.9.0** built for CUDA 12.8 (installed via PyTorch wheels)

  - Install via pip wheel: `pip install --upgrade --force-reinstall "torch==2.9.0+cu128" -f <https://download.pytorch.org/whl/torch_stable.html>` ✅

- bitsandbytes: **0.47.0** — build from source so the CUDA backend binary matches the toolchain:

  - `pip install --no-binary :all: bitsandbytes==0.47.0` ✅

- torch-c-dlpack-ext: improves dlpack/FP8 interop; install via pip: `pip install torch-c-dlpack-ext` ✅

- vLLM: **0.12.0** (pip) and FlashInfer **0.5.3** for FP8 kernels if used

- Numba + NumPy: numba **0.61.2** requires **numpy <= 2.2.x** (we recommend `numpy==2.2.4`) — mismatched NumPy will cause engine init errors.

Common startup troubleshooting:

- If vLLM aborts with import or custom-op errors, check:

  - `python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"`

  - `python -c "import bitsandbytes; print(bitsandbytes.__file__)"` (verify binary present)

  - `python -c "import numba, numpy; print(numba.__version__, numpy.__version__)"` (numba needs numpy<=2.2)

- If you see `Port 7060 is already in use` the launcher will try the next port (7061) automatically; check which port the API binds to in `run/vllm_mistral_7b.log`.

- If model downloads fail due to gated HF access, set `HF_TOKEN` in `global.env` (or export it in your shell) before starting vLLM.

Quick reproducible fix I used locally (inside `justnews-py312`):

```bash

## Install torch wheel for CUDA 12.8

pip install --upgrade --force-reinstall "torch==2.9.0+cu128" -f <https://download.pytorch.org/whl/torch_stable.html> pip
install torch-c-dlpack-ext

## Build bitsandbytes to match CUDA

pip install --no-binary :all: bitsandbytes==0.47.0

## Ensure numpy/numba compatibility

pip install --upgrade --force-reinstall numpy==2.2.4 numba==0.61.2

## Then start vLLM

./scripts/launch_vllm_mistral_7b.sh

```text

If you'd like, I can add a short CHANGELOG entry documenting these env pins and
the exact pip commands used.

## VRAM Budget

Breakdown for 24GB RTX 3090:

- **Base model (AWQ 4-bit)**: ~15–18GB

- **KV cache** (3072 context, batch 1–2): ~2–3GB

- **Overhead**: ~1–2GB

**Total**: 18–23GB (tight but workable)

### Recommendations

- Keep `--max-model-len` ≤ 4096 (3072 is safer).

- Set `--gpu-memory-utilization 0.90` to reserve headroom.

- Use batch size 1–2; avoid higher concurrency.

- Monitor with `nvidia-smi` during inference.

## Fallback Mode

If vLLM is unavailable (server down, OOM, etc.), agents fall back to:

- **Base**: `mistralai/Mistral-7B-Instruct-v0.3`

- **Adapters**: `mistral_<agent>_v1` from ModelStore

Set `fallback.enabled: true` in `config/vllm_mistral_7b.yaml` (default).

## Troubleshooting

### vLLM Server Won't Start

- **OOM**: Reduce `--max-model-len` or `--gpu-memory-utilization`.

- **Model not found**: Check `HF_TOKEN` is set and you have access to gated model.

- **Port in use**: Change `VLLM_PORT` to a free port.

### Slow Inference

- Expected: 32B is 4–5× slower than 7B.

- Check GPU utilization with `nvidia-smi`.

- Reduce context length or batch size.

### Adapter Not Loading

- Ensure adapter path exists in `model_store/adapters/<agent>/<adapter_name>/`.

- Check `VLLM_ENABLE_LORA=true` and `VLLM_LORA_MODULES` is set.

- Verify adapter was trained with compatible LoRA config.

## Next Steps

1. **Train pilot adapter**: Start with one agent (e.g., synthesizer) to validate VRAM fit and quality.

1. **Benchmark latency**: Compare inference time vs. Mistral-7B+adapters.

1. **Quality eval**: Run evals on Qwen2-32B vs. Mistral-7B to quantify quality gain.

1. **Scale adapters**: Train remaining 7 adapters and publish to ModelStore.

1. **Production toggle**: Keep `VLLM_ENABLED=false` for now; enable after validation.

## References

- vLLM docs: <https://docs.vllm.ai/>

- Qwen2 model card: <https://huggingface.co/Qwen/Qwen2-32B-Instruct-AWQ>

- QLoRA paper: <https://arxiv.org/abs/2305.14314>

- ModelStore setup: `docs/operations/SETUP_GUIDE.md`
