Mistral‑7B adapter rollout & perf testing
=========================================

This document describes the test & rollout flow for adopting a single base
Mistral‑7B model with per‑task adapters (LoRA/QLoRA) and how to experiment with
worker pool sizing and performance on RTX‑3090 nodes.

Files added
- scripts/perf/simulate_concurrent_inference.py — multi‑worker inference tester (stub-friendly)
- scripts/ops/adapter_worker_pool.py — spawn warm worker pool processes that load base+adapter

Quick smoke tests (developer machine or GPU node)

1) Dry-run mode (no heavy downloads). This uses the stub scorer so you can
   exercise concurrency safely:

```bash
RE_RANKER_TEST_MODE=1 python scripts/perf/simulate_concurrent_inference.py --workers 4 --requests 400
```

2) Spawn a warm pool using the stub (good to estimate concurrency patterns):

```bash
RE_RANKER_TEST_MODE=1 python scripts/ops/adapter_worker_pool.py --workers 3 --hold 300
# watch 'nvidia-smi' and observe memory/compute while the pool is warm
```

3) Real model test (ONLY on GPU node with CUDA + bitsandbytes):

```bash
export RE_RANKER_TEST_MODE=0
export RE_RANKER_MODEL=mistralai/Mistral-7B-Instruct
# simulate 3 slow workers each doing 30 requests
python scripts/perf/simulate_concurrent_inference.py --workers 3 --requests 30 --model $RE_RANKER_MODEL

# or warm a pool with an adapter
python scripts/ops/adapter_worker_pool.py --workers 2 --model $RE_RANKER_MODEL --adapter modelstore/agents/synthesizer/adapters/mistral_synth_v1 --hold 600
```

Interpreting the numbers
- Watch GPU memory (nvidia-smi) while warming: ensure base + adapters fit in 24GB and observe headroom for activations.
- Use `simulate_concurrent_inference` p95/p50 to decide pool size (target p95 latency & throughput).

Pool sizing guidance (empirical)
- On a single RTX 3090 (24GB) with Mistral‑7B int8: a single base model instance uses ~6–9GB. Each worker process that holds base + adapter will add ~0.5–1.0GB overhead (depending on CUDA memory fragmentation & activations). A safe small pool is 1–3 workers per GPU; tune with perf tests.

Next ops to add
- Add a GPU Orchestrator policy that keeps 1 base model resident and spawns adapter workers on demand.
- Add monitoring/alerts (prometheus metrics) for adapter load, p95 latency, and OOM events.

Latest rollout updates — Fact Checker & Critic
----------------------------------------------
- ModelStore now hosts accuracy-critical adapters at `fact_checker/adapters/mistral_fact_checker_v1` and `critic/adapters/mistral_critic_v1`; both entries are wired through `AGENT_MODEL_MAP.json` so the orchestrator preloads them alongside the existing synthesizer/summarization adapters.
- Fact Checker still couples the adapter with its mpnet retrieval stack. When testing locally, set `RE_RANKER_TEST_MODE=1` so CI-safe stubs load while the adapter path is validated via `pytest tests/agents/test_fact_checker.py`.
- Critic uses the same base snapshot with the `mistral_critic_v1` adapter to score drafts before Chief Editor review. Warm pools can be sanity-checked with:

```bash
MODEL_STORE_ROOT=/opt/justnews/model_store RE_RANKER_TEST_MODE=0 \
   python scripts/ops/adapter_worker_pool.py \
      --workers 2 \
      --model base_models/versions/v20251123-mistral-v0.3 \
      --adapter critic/adapters/mistral_critic_v1 \
      --hold 240
```

- Keep legacy DistilRoBERTa/Flan weights in `AGENT_MODEL_RECOMMENDED.json` as retrieval fallbacks until the new adapters clear sustained production burn-in. Update the manifest `training_summary.json` whenever we retrain either adapter so we can track provenance and align monitoring alerts with exact versions.

Latest rollout updates — Journalist, Chief Editor, Reasoning, Synthesizer
------------------------------------------------------------------------
- Shared adapter helpers now live in `agents/common/base_mistral_json_adapter.py` with per-agent wrappers in `agents/<agent>/mistral_adapter.py`. Each wrapper sets its own disable flag (for example `JOURNALIST_DISABLE_MISTRAL=1`) so you can fall back to the legacy pipeline without code edits.
- `AGENT_MODEL_MAP.json` entries for these agents include `variant_preference` hints (int8 vs fp16) so the GPU orchestrator and `start_agent_worker_pool()` automatically preload the right model+adapter pair. Use `python -m agents.gpu_orchestrator.gpu_orchestrator_engine --dry-run` to verify metadata parsing before shipping new adapters.
- When testing locally, you can instantiate the adapters directly inside `python -m pytest tests/agents/test_mistral_adapters.py -k <agent>`; the tests stub `_chat_json` so they never attempt a real model load yet still validate prompt wiring.
- Production warm pools should be requested via the orchestrator; the developer helper `scripts/ops/adapter_worker_pool.py` is still useful for on-node sizing. Pass the `--adapter` path emitted by `AGENT_MODEL_MAP.json` (or read it via `agents/common/model_loader.get_agent_model_metadata()`) to guarantee you test the same path used by the agents.
- Add smoke fixtures that feed representative payloads to each adapter to keep JSON schema stability under CI. See `tests/agents/test_mistral_adapters.py` for working examples and extend it as new adapters come online.
- For ModelStore validation without GPU downloads, set `MODEL_STORE_DRY_RUN=1` (or `DRY_RUN=1`). The loader will verify base + adapter paths and manifes ts without invoking transformers/Peft. CI uses `tests/common/test_model_store_dry_run.py` to exercise this path.

Latest rollout updates — Analyst & Re-ranker
--------------------------------------------
- Analyst sentiment/bias judgments now use the shared adapter wrapper while preserving the existing RoBERTa heuristics as fallback paths. The adapter normalizes JSON responses into the long-lived `AdapterResult` structure so `analyst_engine` caching stays intact.
- Re-ranker helper `agents/tools/re_ranker_7b.py` prefers the shared adapter (with `RE_RANKER_DISABLE_MISTRAL` as an escape hatch) before falling back to the historical AutoModel heuristic or deterministic stub (`RE_RANKER_TEST_MODE=1`). The legacy `agents/tools/7b_re_ranker.py` now re-exports the canonical helper for consistency.
- CI smoke tests (`tests/agents/test_mistral_adapters.py`) include analyst and re-ranker coverage to guard prompt/JSON drift without loading heavy weights. Extend those fixtures with new schemas as adapters evolve.
