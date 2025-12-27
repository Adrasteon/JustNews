# Model refactor plan — adopt Mistral‑7B + per‑agent adapters

Status: draft

Goal ------ Create a practical, low‑risk path to standardize generation & reasoning across JustNews on a single high
quality open-source base model (Mistral‑7B) with small per‑agent adapters (LoRA / QLoRA / PEFT). Keep specialized models
where they make sense (embeddings, multi‑modal LLaVA), and ensure the GPU Orchestrator, ModelStore and CI pipelines are
updated to support this rollout.

High‑level approach ---------------------

- Adopt a single canonical, publicly available base model: Mistral‑7B (or a locked, approved checkpoint variant).

- Use small per‑agent adapters (LoRA / QLoRA) stored in ModelStore for agent-specific tuning.

- Keep embedding and multi‑modal agents on specialized weights (sentence‑transformers, LLaVA). Use Mistral for pure text generation / reasoning / chain-of-thought tasks.

- Make Orchestrator model-aware: preload base + adapters, use model metadata to size pools, prefer quantized variants where available.

Why this change -----------------

- Maximizes reuse of large model capacity across agents, lowers operational complexity, and reduces overall storage/management overhead by centralizing base weights and storing tiny adapters per agent.

- Adapter-first workflow allows rapid iterative training on single GPUs (RTX 3090) via QLoRA/LoRA and avoids cross‑task weight conflicts.

Scope & affected systems (inventory) ------------------------------------- Files & components inspected
(representative):

- Agents that use or can benefit from 7B causal models (generation/reasoning):

  - `agents/synthesizer/` — text generation, summarisation.

  - `agents/journalist/` — article assembly (generation derivative flows).

  - `agents/chief_editor/` — editorial rewrite/judgement.

  - `agents/reasoning/`, `agents/critic/`, `agents/hitl_service/` — reasoning & HITL interactions; Critic now ships with the `mistral_critic_v1` adapter for higher-accuracy editorial gating while retaining lightweight fallback tools for outage scenarios.

  - `agents/fact_checker/` — accuracy-critical claim verification now uses the shared Mistral base via the `mistral_fact_checker_v1` adapter for long-form evidence synthesis; retrieval/semantic search continues to rely on mpnet-sized encoders.

  - `agents/analyst/` — bias/sentiment/persuasion scoring now prioritizes accuracy over latency, so add a Mistral adapter-powered tool alongside existing RoBERTa fallbacks.

  - Re-ranker tooling: `agents/tools/7b_re_ranker.py`, `scripts/perf/simulate_concurrent_inference.py`.

- Agents primarily using embeddings or multi-modal models (these keep specialized models):

  - `agents/scout/`, `agents/memory/` — embeddings (sentence‑transformers) — do not replace with Mistral.

  - `agents/newsreader/` — multimodal LLaVA — keep LLaVA for vision tasks.

- Orchestrator & infra: `agents/gpu_orchestrator/gpu_orchestrator_engine.py`, `main.py`, systemd/service templates and startup scripts (these will be updated to: read model metadata, configure preload policy, and support Mistral workflows).

- ModelStore & publish helpers: `agents/common/model_store.py`, `scripts/publish_hf_to_model_store.py`, `agents/common/model_loader.py`.

- Shared adapter tooling: `agents/common/base_mistral_json_adapter.py` plus each agent's `mistral_adapter.py` wrapper, providing JSON-centric prompts and automatic base fallback.

- Perf & training: `scripts/perf/`, `scripts/ops/adapter_worker_pool.py`, `scripts/train_qlora.py`.

- Tests: `tests/unit/test_gpu_orchestrator_workers_api.py`, re-ranker tests, adapter pool tests — will need updates to test with ModelStore mapping and adapter paths.

Desired final state --------------------

- Mistral‑7B base published in ModelStore and accessible from production nodes.

- Per-agent adapter artifacts (LoRA/QLoRA) produced and published in ModelStore for: synthesizer, re-ranker, journalist, chief_editor, reasoning, and analyst agents (analyst retains legacy RoBERTa tooling as a fallback but defaults to the new Mistral adapter for production decisions).

- Orchestrator automatically uses model metadata (approx_vram_mb, quantized_variants, peft_support) for preloading and pool sizing, and supports adapter hot-swapping.

- Agents transparently load the appropriate variant (ModelStore or HF) and prefer ModelStore snapshots when `MODEL_STORE_ROOT` is configured.

- CI workflows for publishing adapters and for verifying ModelStore health, preflight checks for GPU/conda bitsandbytes availability, tests and a DRY_RUN to ensure no large artifacts are committed accidentally.

Detailed step-by-step plan ---------------------------

Overview of Phases

  - Phase 0: Preparation & safety checks

  - Phase 1: ModelStore + artifact publishing

  - Phase 2: Adapter training & storage pipeline

  - Phase 3: Orchestrator + agent integration

  - Phase 4: Testing, perf tuning & rollout

  - Phase 5: CI, monitoring & maintenance

Phase 0 — Preparation & safety checks ------------------------------------- 1) Licensing & checkpoint selection
(priority)

  - Confirm the exact Mistral checkpoint (HF model card) and license (ensure it is acceptable for production training & distribution).

  - Canonical checkpoint + license are now pinned to `mistralai/Mistral-7B-Instruct-v0.3` (Apache-2.0). Reference metadata lives in `models/metadata/mistral-7b-instruct-v0.3.json` for downstream tooling.

2) Host readiness checklist

  - Confirm that GPU nodes have required CUDA + drivers and that bitsandbytes native binaries are built against target CUDA (documented in repo). Add an automated verification script for `bitsandbytes` compatibility in `infrastructure/systemd/preflight.sh` or a new preflight utility.

  - Export `BNB_CUDA_VERSION=122` (now tracked in `global.env`) on all hosts so the runtime loads the custom CUDA 12.2 bitsandbytes wheel until upstream publishes CUDA 12.4 builds; document overrides for environments that later upgrade toolkits. See `docs/bitsandbytes_cuda122_wheel.md` for the full build + troubleshooting guide.

  - Confirm `MODEL_STORE_ROOT` is available and writable on target nodes; ensure backup & snapshot cadence is documented.

3) Repo & QA housekeeping

  - `AGENT_MODEL_MAP.json` now exists and seeds entries for `synthesizer` + `re_ranker` agents pointing at the canonical base and placeholder adapter slots. Continue extending it for journalist, chief_editor, reasoning, **and analyst** so all critical decision-makers pull from the shared base.

  - Add a `docs/mistral_adapter_rollout.md` -> already present; augment with an entry describing canonical base + adapter naming conventions.

Phase 1 — ModelStore publishing -------------------------------- Goal: publish canonical Mistral base weights and a
canonical path / layout in ModelStore.

Steps: 1) Create a canonical ModelStore version for the Mistral base

    - ✅ Completed: published `mistralai/Mistral-7B-Instruct-v0.3` as `base_models/versions/v20251123-mistral-v0.3` using the metadata-aware script. All GPU hosts should replicate this command:

```bash MODEL_STORE_ROOT=/opt/justnews/model_store HF_TOKEN=$HF_TOKEN \ python
scripts/publish_hf_to_model_store.py \ --agent base_models \ --model
mistralai/Mistral-7B-Instruct-v0.3 \ --version v20251123-mistral-v0.3 \
--metadata models/metadata/mistral-7b-instruct-v0.3.json ```

    - Current symlink verifies to that version; checksum recorded in manifest (`847e9311…b4dc8`).

2) Add model metadata & manifest

   - ✅ Manifest now embeds `models/metadata/mistral-7b-instruct-v0.3.json` with Apache-2.0 license, tokenizer v3, VRAM for fp16/int8/4bit, and adapter guidance. Update the JSON as VRAM measurements evolve; rerun `publish_hf_to_model_store.py --force` for new versions when values change materially.

3) Make quantized variants if possible (optional but recommended)

   - Optionally prepare pre-quantized versions for the target CUDA / bnb configuration (exported artifact or alternate snapshot path). This will avoid slow downloads and reduce runtime compilation issues.

4) Publish initial adapters placeholders

   - ✅ Placeholder directories now live in ModelStore:

       - `synthesizer/adapters/mistral_synth_v1` — README describes expected PEFT files.

       - `re_ranker/adapters/mistral_re_ranker_v1` — README + reserved path for reranker adapter.

   - Use these as publish targets once Phase 2 training jobs produce real adapters; extend to journalist/chief_editor as their plans firm up.

Phase 2 — Adapter training & storage pipeline
---------------------------------------------- Goal: produce small PEFT adapter
artifacts per agent and store them in ModelStore.

Steps: 1) Add training templates and reproducible QLoRA/LoRA pipelines

   - ✅ `scripts/train_qlora.py` now exposes `--agent`, `--adapter-name`, `--adapter-version`, `--train-files`, hyper-parameter knobs, and `--publish` to push adapters directly into ModelStore. It saves `training_summary.json` alongside the adapter payload for auditing.

   - Defaults target RTX 3090 int8/4bit configs (LoRA r=64, alpha=16, gradient checkpointing optional). Review `--max-train-samples` + `--dry-run` for CI-safe smoke tests.

   - See `train_qlora/README.md` for usage recipes, dependency notes, and publishing flow.

2) Example adapter training flow (synthesizer)

    - Run a QLoRA script using a curated fine-tuning dataset for the synthesizer agent (adjust dataset + hyper-params as needed):

```bash MODEL_STORE_ROOT=/opt/justnews/model_store \ conda run -n
${CANONICAL_ENV:-justnews-py312} python scripts/train_qlora.py \ --agent synthesizer \ --adapter-name mistral_synth_v1 \
--model_name_or_path mistralai/Mistral-7B-Instruct-v0.3 \ --train-files data/synth_finetune.jsonl \ --output_dir
output/adapters/mistral_synth_v1 \ --epochs 3 \ --train-batch-size 1 \ --gradient-accumulation 8 \ --publish ```

    - The `--publish` flag now copies `output/adapters/mistral_synth_v1` into the `synthesizer` ModelStore namespace and writes adapter metadata into the manifest. Use `--adapter-version` when you need a deterministic version tag; otherwise the script timestamps it automatically.

3) QA & validation

  - Add unit tests that load adapter via `PeftModel.from_pretrained()` against the base model using `RE_RANKER_TEST_MODE` toggles for CI.

  - Add a sample inference script to smoke‑test that base + adapter load and produce plausible outputs.

Phase 3 — Orchestrator + agent integration ------------------------------------------- Goal: make the orchestrator,
agents, and ModelLoader handle Mistral + adapters cleanly and enable warm pools.

Steps: 1) ModelStore metadata support in orchestrator

  - ✅ `agents/gpu_orchestrator/gpu_orchestrator_engine.py` now parses `AGENT_MODEL_MAP.json`, resolves each entry's manifest via `agents/common/model_loader.get_agent_model_metadata`, and tracks the metadata (approx_vram_mb, quantized_variants) when kicking off preload jobs. This ensures the orchestration layer knows exactly which base snapshot + adapter paths exist before provisioning pools.

  - ✅ Captured metadata now flows into pool sizing logic: worker provisioning prefers `bnb-int8` variants whenever a policy or caller marks `allow_quantized=true`, and falls back to fp16 if quantized entries are missing. The orchestrator also exposes `start_agent_worker_pool()` so call sites can request the correct variant explicitly.

2) AGENT_MODEL_MAP.json & AGENT_MODEL_RECOMMENDED.json

  - ✅ `AGENT_MODEL_MAP.json` now drives both loader and orchestrator. `agents/common/model_loader.py` resolves base + adapter locations (including ModelStore versions) and exposes `load_transformers_with_adapter()` plus a metadata helper for consumers. The orchestrator consumes the same map when preloading entries, ensuring one source of truth for base/adapters.

  - ✅ Journalist, chief_editor, reasoning, synthesizer, critic, and fact_checker entries now capture `variant_preference` hints so policy selection understands whether to go straight to int8 or reserve fp16 capacity. `AGENT_MODEL_RECOMMENDED.json` is down-scoped to fallback references only.

  - Continue extending the map for remaining adapter targets (analyst, re_ranker) as those adapters move out of staging. Keep recommended entries in sync only for legacy fallbacks.

3) Agent code changes

  - ✅ Shared adapter plumbing now lives in `agents/common/base_mistral_json_adapter.py`, reused by per-agent helpers (`agents/journalist/mistral_adapter.py`, `agents/chief_editor/mistral_adapter.py`, `agents/reasoning/mistral_adapter.py`, `agents/synthesizer/mistral_adapter.py`). These helpers encapsulate prompts + JSON coercion while relying on the loader’s caching logic.

  - ✅ `journalist_engine`, `chief_editor_engine`, `reasoning_engine`, and `synthesizer_engine` now call their respective adapters, attach parsed outputs to the agent context, and guard fallbacks when adapters are unavailable.

      - ✅ Analyst sentiment/bias flows now leverage the shared adapter via `agents/analyst/mistral_adapter.py`, normalizing JSON replies into the existing `AdapterResult` structure while keeping RoBERTa/heuristic paths as fallbacks. The re-ranker tooling (`agents/tools/re_ranker_7b.py`) now prefers the shared adapter before falling back to the older AutoModel heuristic or deterministic stub.

  - Adapter coverage checklist for the newly migrated agents:

      - Fact Checker smoke tests still cover the adapter load path via `tests/agents/test_fact_checker.py` with `RE_RANKER_TEST_MODE=1`, ensuring prompt formatting and retrieval fallbacks behave in CI.

      - Critic regression harness exercises `agents/critic/critic_engine.py` through the shared loader helper so the orchestrator preloads the adapter before policy checks execute.

        - New shared smoke tests live in `tests/agents/test_mistral_adapters.py`, covering journalist, chief_editor, reasoning, synthesizer, analyst, and the re-ranker adapter prompt wiring. Extend the suite as additional adapters ship.

4) Warm pool & adapter hot-swap

  - ✅ `gpu_orchestrator_engine` worker pool loaders now apply both base and adapter loading sequence (AutoModelForCausalLM.from_pretrained + PeftModel.from_pretrained) so warm pools start with adapters already mounted.

  - ✅ `start_agent_worker_pool()` and the existing `/workers/pool/{pool_id}/swap` endpoint were validated against Mistral adapter sizes. Remaining work is exercising hot-swap with multi-adapter agents (synthesizer task router) before GA.

5) Orchestrator policy updates

  - ✅ `model_vram` and `quantized_variants` values now live in the metadata cache used by policy evaluation, so rules prefer int8 when `allow_quantized=true` and avoid overcommitting GPUs lacking memory headroom.

  - Next: layer watchdog metrics (Phase 5) to ensure policy drift is caught automatically.

Phase 4 — Testing, perf tuning & rollout ---------------------------------------- 1) Perf runs and warm pool sizing

  - Use `scripts/perf/simulate_concurrent_inference.py` and `scripts/ops/adapter_worker_pool.py` to run sweeps on production-like GPU nodes. Save standard CSVs for reproducibility in `scripts/perf/results`.

  - 2025-11-25 local stub sweep: `scripts/perf/simulate_concurrent_inference.py --requests 180 --sweep --repeat 2` (with `RE_RANKER_TEST_MODE=1`) produced linear scaling from 1→6 workers with p50≈2.06 ms and no GPU usage; raw CSV/JSON artifacts live in `scripts/perf/results/2025-11-25-sim_sweep_stub.{csv,json}` for reproducibility.

  - 2025-11-25 adapter pool stub soak: `scripts/ops/adapter_worker_pool.py --workers 3 --hold 5` validated the worker launcher wiring and staggered spin-up; next run should point at real adapter paths once GPU hardware is available.

      - 2025-11-25 RTX3090 fp16 sweep (real model): `scripts/perf/simulate_concurrent_inference.py --requests 120 --sweep --sweep-max 4 --repeat 1 --model mistralai/Mistral-7B-Instruct-v0.3` now runs end-to-end on the local GPU after removing the mismatched `bitsandbytes` package. Results: p50 latencies scale from 31 ms (1 worker) → 101 ms (4 workers) with averages following the same curve; artifacts saved to `scripts/perf/results/2025-11-25-real_fp16.{csv,json}`.

      - 2025-11-25 CUDA 12.2 int8 validation: after rebuilding bitsandbytes and exporting `BNB_CUDA_VERSION=122`, running `scripts/perf/simulate_concurrent_inference.py --requests 20 --sweep --sweep-max 2 --model mistralai/Mistral-7B-Instruct-v0.3 --output-csv scripts/perf/results/2025-11-25-mistral-bnb122.csv --output-json scripts/perf/results/2025-11-25-mistral-bnb122.json` completed on GPU with p50 ≈165 ms (1 worker) and ≈267 ms (2 workers). These artifacts now serve as the baseline for CUDA‑12.2/bitsandbytes int8 pools.

      - 2025-11-25 CUDA 12.2 int8 sweep (1–4 workers): `scripts/perf/simulate_concurrent_inference.py --requests 80 --sweep --sweep-max 4 --model mistralai/Mistral-7B-Instruct-v0.3 --output-csv scripts/perf/results/2025-11-25-mistral-bnb122-sweep.csv --output-json scripts/perf/results/2025-11-25-mistral-bnb122-sweep.json` with `BNB_CUDA_VERSION=122` shows roughly linear degradation as concurrency increases (p50 160 ms → 561 ms across 1→4 workers) and confirms the rebuilt bitsandbytes path stays stable under longer loads.

      - 2025-11-25 fp16 control sweep: setting `BNB_DISABLE=1` to skip bitsandbytes and running the same sweep (`scripts/perf/results/2025-11-25-mistral-fp16-sweep.{csv,json}`) produces p50 latencies from ≈31 ms (1 worker) to ≈101 ms (4 workers), giving us a clear delta between fp16 and int8 behavior on the same RTX3090 host.

      - 2025-11-25 worker-pool real soak: updated `scripts/ops/adapter_worker_pool.py` to fall back to float16 when bitsandbytes is unavailable, then launched `RE_RANKER_TEST_MODE=0 python scripts/ops/adapter_worker_pool.py --workers 2 --model mistralai/Mistral-7B-Instruct-v0.3 --hold 30`. Both processes loaded the 7B weights and held steady for the duration, validating the helper end-to-end on RTX3090.

    - Leverage the new metadata (approx_vram_mb + variant_preference) to benchmark both fp16 and int8 pools. For RTX 3090 expect int8 warm pools sized 1–2 per GPU for latency-sensitive agents; document when policies must override to fp16. Capture both stub and real-run artifacts, noting that real GPU runs (int8 vs fp16) are still TBD pending access to production-class hardware.

    - **Next hardware run (todo):** on a RTX 3090 node with ModelStore mounted, run the fp16/int8 sweep pairs below for both synthesizer and re-ranker adapters, each time setting `MODEL_STORE_ROOT=/opt/justnews/model_store` and exporting the agent metadata (`python -c "from agents.common import model_loader; print(model_loader.get_agent_model_metadata('synthesizer'))"`). Commands to queue once GPUs are free:

```bash
       # Int8 sweep (uses variant_preference=bnb-int8). Adapter paths pulled from AGENT_MODEL_MAP.
MODEL_STORE_ROOT=/opt/justnews/model_store RE_RANKER_TEST_MODE=0 \ conda run -n
${CANONICAL_ENV:-justnews-py312} python
scripts/perf/simulate_concurrent_inference.py \ --model
mistralai/Mistral-7B-Instruct-v0.3 --adapter
model_store/synthesizer/adapters/mistral_synth_v1 \ --requests 240 --sweep
--sweep-max 8 --repeat 3 --output-csv
scripts/perf/results/2025-11-25-synth_int8.csv

       # Matching fp16 control (set BNB_DISABLE=1 to force fp16 path if needed)
MODEL_STORE_ROOT=/opt/justnews/model_store RE_RANKER_TEST_MODE=0 BNB_DISABLE=1 \
conda run -n ${CANONICAL_ENV:-justnews-py312} python
scripts/perf/simulate_concurrent_inference.py \ --model
mistralai/Mistral-7B-Instruct-v0.3 --adapter
model_store/synthesizer/adapters/mistral_synth_v1 \ --requests 240 --sweep
--sweep-max 8 --repeat 3 --output-csv
scripts/perf/results/2025-11-25-synth_fp16.csv

       # Worker-pool soak (int8) with live adapter path
MODEL_STORE_ROOT=/opt/justnews/model_store RE_RANKER_TEST_MODE=0 \ conda run -n
${CANONICAL_ENV:-justnews-py312} python scripts/ops/adapter_worker_pool.py \
--workers 4 --model mistralai/Mistral-7B-Instruct-v0.3 \ --adapter
model_store/re_ranker/adapters/mistral_re_ranker_v1 --hold 900 ``` Capture
`nvidia-smi` before/after each run and append summaries + artifacts into
`scripts/perf/results/` (naming each file `{agent}_{variant}_{yyyymmdd}.csv`).
Also run `sudo scripts/ops/enable_kernel_logging.sh` once per perf host so
journald persists kernel/Xid events and rsyslog mirrors them into
`/var/log/kern.log`, letting us read `journalctl -k -b -1 | grep -i xid` even
after a forced power cycle.

2) Health checks & tests

   - ✅ Initial adapter smoke coverage now lives in `tests/agents/test_mistral_adapters.py`, which stubs `_chat_json` for journalist, chief_editor, reasoning, synthesizer, analyst, and re-ranker flows. Continue expanding with fact_checker/critic fixtures and DRY_RUN coverage.

   - ✅ Added `tests/common/test_model_store_dry_run.py` which sets `MODEL_STORE_DRY_RUN=1` to ensure the loader resolves ModelStore paths, manifests, and adapter locations without touching HF/downloads. Keep extending this path for future agents.

3) Canary rollouts

   - Roll out Mistral+adapter to a limited set of hosts / agents: start with `re-ranker` and `synthesizer` on a single GPU node, run steady-state traffic simulation, verify memory/p95 and error rates.

   - Deploy broader progressively to journalist, chief_editor. Keep ability to fallback to `AGENT_MODEL_RECOMMENDED.json` or previous model for critical agents if issues arise.

   - **Canary playbook (next action):**
     1. Preload adapters via GPU orchestrator API: `python agents/gpu_orchestrator/main.py start_agent_worker_pool --agent re_ranker --variant bnb-int8 --num-workers 2 --hold-seconds 1800`.
     1. Route 5% of production-like traffic (or synthetic replay via `scripts/perf/gpu_activity_agent.py`) through the canary pool while mirroring to the legacy model; capture p50/p95/p99 and error counts.
     1. If metrics stay within ±5% for 30 min, scale workers to 4 and expand traffic to 25%; otherwise trigger rollback by `stop_worker_pool` and re-point routing to the previous recommendation entry.
     1. Repeat for synthesizer; once both are stable, replicate the sequence for journalist and chief_editor, then resume Phase 5 tasks (monitoring + CI). Document every canary in `docs/mistral_adapter_rollout.md`.

Phase 5 — CI, monitoring & maintenance -------------------------------------- 1)
CI & validation

   - Add a pipeline job to validate ModelStore snapshots: `scripts/check_model_store.py` that ensures `manifest.json` presence, `approx_vram_mb` within reasonable bounds and optionally checks an adapter can be loaded in DRY_RUN. Include variant_preference + quantized_variants validation so orchestrator policies stay in sync.

   - Add pre-commit checks and CI rule to reject accidental commits of large model artifacts (binaries). Your repo already ignores `artifacts/` and added some protections; expand CI to detect tracked large files.

2) Observability & alerts

   - Add orchestrator Prometheus metrics and alerts for OOM events, `worker_pool_evictions`, `model_preload_failures`, high p95 latency, adapter hot-swap failures, and per-variant pool depletion so we catch mismatched int8/fp16 demand. Build dashboards in `monitoring/dashboards`.

3) Operational runbook

   - Add `docs/ops/mistral_rollout_runbook.md` with commands, troubleshooting steps (e.g., bitsandbytes compile troubleshooting), emergency rollback steps, and how to restore the previous model set quickly from ModelStore or HF.

4) Backup and store management

   - Add periodic backups for ModelStore (S3/remote storage) and a rotation policy. The repo already includes `models/model_store_guide.md`; add Mistral-specific notes including expected large weight sizes and backup cadence.

Fallback / rollback plans -------------------------

- Any agent should be able to fall back to a prior model defined in `AGENT_MODEL_MAP.json` or `AGENT_MODEL_RECOMMENDED.json` if `STRICT_MODEL_STORE` or load fails.

- Default to test stub (`RE_RANKER_TEST_MODE`) in CI.

Timeline & milestones (example) --------------------------------

- Week 1: Phase 0 + Phase 1 (model selection, ModelStore base publish, manifest). Validate on 1 GPU node.

- Week 2: Phase 2 (train synthesizer + re-ranker adapters; publish to ModelStore). Add tests & CI dry-run.

- Week 3: Phase 3 (agent & orchestrator changes + hot-swap testing). Canary to small host group.

- Week 4: Phase 4 & 5 (perf tuning, full rollout, CI + monitoring finalized).

Files and repo places to change (detailed)
----------------------------------------

- `scripts/publish_hf_to_model_store.py` — use to publish base & adapter snapshots.

- `agents/common/model_store.py` — used for atomic staging/finalize; add expected adapter manifest schema and validation helpers.

- `agents/common/model_loader.py` — extend to expose `load_transformers_with_adapter(base, adapter)` and handle strict ModelStore errors.

- `agents/common/base_mistral_json_adapter.py` + `agents/*/mistral_adapter.py` — shared JSON adapter helpers each agent now consumes; keep prompts + schema in these modules to avoid drift.

- `agents/gpu_orchestrator/gpu_orchestrator_engine.py` — read model manifest, use `approx_vram_mb`, prefer quantized variants and enforce pool policy.

- `AGENT_MODEL_MAP.json` / `AGENT_MODEL_RECOMMENDED.json` — create/extend with Mistral entries, base + adapters, and recommended variants.

- `scripts/train_qlora.py` — add flags and ModelStore publish option.

- `scripts/ops/adapter_worker_pool.py` & `scripts/perf/*` — adopt Mistral-based tests and add a `--adapter` CLI option (already present) and a `--variant` selection (int8 vs fp16).

- Add CI tests in `tests/*` and `pytest.ini` to include ModelStore DRY_RUN validation.

- Add new docs: `docs/model_refactor.md` (this file), `docs/ops/mistral_rollout_runbook.md`, and update `docs/embed_model_assess.md` / `docs/mistral_adapter_rollout.md` with final steps.

Risks & mitigations ---------------------

- CPU/gpu OOMs and mismatched bitsandbytes binary → Mitigate by adding preflight checks and pre-compiled binaries early, and provide fallback to float16/auto device_map.

- Model license / legal concerns → verify HF model card and team legal approval; keep alternate candidate models (MPT, Pythia) in case of restrictions.

- Runbook complexity (hot-swap failure) → keep safe rollbacks and default fallbacks in `AGENT_MODEL_MAP.json`.

Acceptance criteria & verification checklist
------------------------------------------- Before closing migration for a given
agent: all of these must be satisfied: 1) Base model & adapter published and
verified in ModelStore (manifest present & checksum verified). 2) Agent loads
model+adapter successfully on a production node in non-test mode. 3)
Orchestrator can preload base+adapter, pick the right variant preference (int8
vs fp16), and create warm pools without OOMs for configured pool sizes. 4) CI
runs smoke tests in DRY_RUN mode validating models/adapters are present and that
base+adapter load path exists. 5) Monitoring captures p95 latency and OOM
failures and alerts are configured.

Appendix — short examples / commands ------------------------------------
Publish base:

```bash
MODEL_STORE_ROOT=/opt/justnews/model_store HF_TOKEN=$HF_TOKEN python scripts/publish_hf_to_model_store.py --agent
base_models --model mistralai/Mistral-7B-v0.3 --version v20251123

```

Train adapter (example):

```bash
conda activate ${CANONICAL_ENV:-justnews-py312} python scripts/train_qlora.py --model_name_or_path
mistralai/Mistral-7B-Instruct --output_dir output/adapters/mistral_synth_v1 --train_files data/synth_finetune.jsonl
--adapter_name mistral_synth_v1 --epochs 3

```

Publish adapter:

```bash
python scripts/publish_hf_to_model_store.py --agent synthesizer --model mistralai/Mistral-7B-v0.3 --version
v20251123-mistral-synth-v1 --model output/adapters/mistral_synth_v1

```

Warm pool test:

```bash
RE_RANKER_TEST_MODE=0 RE_RANKER_MODEL=mistralai/Mistral-7B-v0.3 python scripts/perf/simulate_concurrent_inference.py
--workers 3 --requests 30

```

---

If you'd like, my immediate next actions are:

- A) Publish a canonical Mistral‑7B base into ModelStore on the host (requires HF token / permission), then create adapter stubs for `synthesizer` and `re_ranker` and add AGENT_MODEL_MAP.json entries; or

- B) Implement ModelStore metadata support in the Orchestrator and wiring to prefer quantized variants; or

- C) Add the adapter training + publish CI pipeline and a dry-run test harness.

Pick the next action and I’ll continue — I can implement any of the three
detailed options.
