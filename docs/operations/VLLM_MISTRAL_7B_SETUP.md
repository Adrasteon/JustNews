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
```

### 2. Launch vLLM Server

```bash
# Port 7060 (outside agent range)
./scripts/launch_vllm_mistral_7b.sh
```

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
```

Expected output:
```
Testing health endpoint: http://127.0.0.1:7060/v1/health
✅ Health check passed
Testing models endpoint: http://127.0.0.1:7060/v1/models
✅ Models: ['mistralai/Mistral-7B-Instruct-v0.3']
Testing chat completion: http://127.0.0.1:7060/v1/chat/completions
✅ Chat completion result: 4

✅ All tests passed!
```

### 4. Enable vLLM for Agents

Set `VLLM_ENABLED=true` in `global.env`:

```bash
# In global.env
VLLM_ENABLED=true
```

Agents will now route inference to the vLLM endpoint (`http://127.0.0.1:7060/v1`) instead of local transformers.

## Configuration

### Environment Variables

Key variables in `global.env`:

```bash
# vLLM Mistral-7B Inference Endpoint
VLLM_ENABLED=false           # Set to true to enable
VLLM_BASE_URL=http://127.0.0.1:7060/v1
VLLM_API_KEY=dummy           # vLLM doesn't require auth
VLLM_MODEL=mistralai/Mistral-7B-Instruct-v0.3
VLLM_PORT=7060
```

### vLLM Config File

`config/vllm_qwen2_32b.yaml` contains:
- Endpoint settings (host, port, base URL)
- Per-agent adapter paths (for vLLM LoRA hot-swap)
- Training settings (QLoRA parameters for 24GB 3090)
- Fallback config (Mistral-7B + adapters)

### Agent Model Mappings

#### AGENT_MODEL_MAP.json

- **base_models**: Added `qwen2-32b-awq` entry with vLLM endpoint.
- **vllm_agents**: Separate section for Qwen2-32B + adapter mappings per agent.
  - Each agent (synthesizer, critic, etc.) has a `qwen2_<agent>_v1` adapter.
  - `inference_mode: "vllm"` flag routes to vLLM.

#### AGENT_MODEL_RECOMMENDED.json

- Each agent now has:
  - `default`: Mistral-7B-Instruct-v0.3 (fallback)
  - `vllm_default`: Qwen/Qwen2-32B-Instruct-AWQ (when `VLLM_ENABLED=true`)
- Comment at top documents the toggle.

## Training Per-Agent Adapters

### QLoRA Training on 24GB 3090

Use `scripts/train_qwen2_qlora.py` (historical Qwen2 adapters) or your own adapter training scripts for Mistral adapters. If you have Mistral adapter training scripts, prefer those and set `--model_name_or_path mistralai/Mistral-7B-Instruct-v0.3`.

```bash
conda activate justnews-py312

# Example: train synthesizer adapter
python scripts/train_qwen2_qlora.py \
  --model_name_or_path Qwen/Qwen2-32B-Instruct \
  --config_path config/vllm_qwen2_32b.yaml \
  --train_file data/synth_finetune.jsonl \
  --agent_name synthesizer \
  --adapter_name qwen2_synth_v1 \
  --output_dir output/adapters \
  --max_steps 1000 \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 16 \
  --learning_rate 2e-4 \
  --bf16 \
  --publish
```

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
2. Pass `VLLM_LORA_MODULES` as comma-separated `name=path` pairs:
   ```bash
   VLLM_LORA_MODULES="synthesizer=/home/adra/JustNews/model_store/adapters/synthesizer/qwen2_synth_v1,critic=/home/adra/JustNews/model_store/adapters/critic/qwen2_critic_v1"
   ```
3. Restart vLLM server with `./scripts/launch_vllm_mistral_7b.sh`.

Client code can request a specific adapter via the `model` field in the OpenAI API call (if vLLM is configured to route by adapter name).

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

Set `fallback.enabled: true` in `config/vllm_qwen2_32b.yaml` (default).

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
2. **Benchmark latency**: Compare inference time vs. Mistral-7B+adapters.
3. **Quality eval**: Run evals on Qwen2-32B vs. Mistral-7B to quantify quality gain.
4. **Scale adapters**: Train remaining 7 adapters and publish to ModelStore.
5. **Production toggle**: Keep `VLLM_ENABLED=false` for now; enable after validation.

## References

- vLLM docs: https://docs.vllm.ai/
- Qwen2 model card: https://huggingface.co/Qwen/Qwen2-32B-Instruct-AWQ
- QLoRA paper: https://arxiv.org/abs/2305.14314
- ModelStore setup: `docs/operations/SETUP_GUIDE.md`
