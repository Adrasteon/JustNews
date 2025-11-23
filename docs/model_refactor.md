# Model refactor plan — adopt Mistral‑7B + per‑agent adapters

Status: draft

Goal
------
Create a practical, low‑risk path to standardize generation & reasoning across JustNews on a single high quality open-source base model (Mistral‑7B) with small per‑agent adapters (LoRA / QLoRA / PEFT). Keep specialized models where they make sense (embeddings, multi‑modal LLaVA), and ensure the GPU Orchestrator, ModelStore and CI pipelines are updated to support this rollout.

High‑level approach
---------------------
- Adopt a single canonical, publicly available base model: Mistral‑7B (or a locked, approved checkpoint variant).
- Use small per‑agent adapters (LoRA / QLoRA) stored in ModelStore for agent-specific tuning.
- Keep embedding and multi‑modal agents on specialized weights (sentence‑transformers, LLaVA). Use Mistral for pure text generation / reasoning / chain-of-thought tasks.
- Make Orchestrator model-aware: preload base + adapters, use model metadata to size pools, prefer quantized variants where available.

Why this change
-----------------
- Maximizes reuse of large model capacity across agents, lowers operational complexity, and reduces overall storage/management overhead by centralizing base weights and storing tiny adapters per agent.
- Adapter-first workflow allows rapid iterative training on single GPUs (RTX 3090) via QLoRA/LoRA and avoids cross‑task weight conflicts.

Scope & affected systems (inventory)
-------------------------------------
Files & components inspected (representative):
- Agents that use or can benefit from 7B causal models (generation/reasoning):
  - `agents/synthesizer/` — text generation, summarisation.
  - `agents/journalist/` — article assembly (generation derivative flows).
  - `agents/chief_editor/` — editorial rewrite/judgement.
  - `agents/reasoning/`, `agents/critic/`, `agents/hitl_service/` — reasoning & HITL interactions.
  - Re-ranker tooling: `agents/tools/7b_re_ranker.py`, `scripts/perf/simulate_concurrent_inference.py`.

- Agents primarily using embeddings or multi-modal models (these keep specialized models):
  - `agents/scout/`, `agents/memory/` — embeddings (sentence‑transformers) — do not replace with Mistral.
  - `agents/newsreader/` — multimodal LLaVA — keep LLaVA for vision tasks.

- Orchestrator & infra: `agents/gpu_orchestrator/gpu_orchestrator_engine.py`, `main.py`, systemd/service templates and startup scripts (these will be updated to: read model metadata, configure preload policy, and support Mistral workflows).
- ModelStore & publish helpers: `agents/common/model_store.py`, `scripts/publish_hf_to_model_store.py`, `agents/common/model_loader.py`.
- Perf & training: `scripts/perf/`, `scripts/ops/adapter_worker_pool.py`, `scripts/train_qlora.py`.
- Tests: `tests/unit/test_gpu_orchestrator_workers_api.py`, re-ranker tests, adapter pool tests — will need updates to test with ModelStore mapping and adapter paths.

Desired final state
--------------------
- Mistral‑7B base published in ModelStore and accessible from production nodes.
- Per-agent adapter artifacts (LoRA/QLoRA) produced and published in ModelStore for: synthesizer, re-ranker, journalist, chief_editor, and reasoning agents.
- Orchestrator automatically uses model metadata (approx_vram_mb, quantized_variants, peft_support) for preloading and pool sizing, and supports adapter hot-swapping.
- Agents transparently load the appropriate variant (ModelStore or HF) and prefer ModelStore snapshots when `MODEL_STORE_ROOT` is configured.
- CI workflows for publishing adapters and for verifying ModelStore health, preflight checks for GPU/conda bitsandbytes availability, tests and a DRY_RUN to ensure no large artifacts are committed accidentally.

Detailed step-by-step plan
---------------------------

Overview of Phases
  - Phase 0: Preparation & safety checks
  - Phase 1: ModelStore + artifact publishing
  - Phase 2: Adapter training & storage pipeline
  - Phase 3: Orchestrator + agent integration
  - Phase 4: Testing, perf tuning & rollout
  - Phase 5: CI, monitoring & maintenance

Phase 0 — Preparation & safety checks
-------------------------------------
1) Licensing & checkpoint selection (priority)
   - Confirm the exact Mistral checkpoint (HF model card) and license (ensure it is acceptable for production training & distribution).
   - Choose a canonical checkpoint string to pin in documentation and artifacts (ex: `mistralai/Mistral-7B-v0.3` or the org-approved tag).

2) Host readiness checklist
   - Confirm that GPU nodes have required CUDA + drivers and that bitsandbytes native binaries are built against target CUDA (documented in repo). Add an automated verification script for `bitsandbytes` compatibility in `infrastructure/systemd/preflight.sh` or a new preflight utility.
   - Confirm `MODEL_STORE_ROOT` is available and writable on target nodes; ensure backup & snapshot cadence is documented.

3) Repo & QA housekeeping
   - Add `AGENT_MODEL_MAP.json` (if not present) or update it with explicit entries for the agents we'll migrate. These will contain {agent: [base_model_id, adapters...]} or a richer per-agent structure.
   - Add a `docs/mistral_adapter_rollout.md` -> already present; augment with an entry describing canonical base + adapter naming conventions.

Phase 1 — ModelStore publishing
--------------------------------
Goal: publish canonical Mistral base weights and a canonical path / layout in ModelStore.

Steps:
1) Create a canonical ModelStore version for the Mistral base
   - Use `scripts/publish_hf_to_model_store.py` for agent `synthesizer` (or `base_models` agent placeholder) with a timestamped version label.
   - Example command:
     ```bash
     MODEL_STORE_ROOT=/opt/justnews/model_store HF_TOKEN=$HF_TOKEN \ 
       python scripts/publish_hf_to_model_store.py --agent base_models --model mistralai/Mistral-7B-v0.3 --version v20251123-mistral-v0.3
     ```
   - Confirm `ModelStore.finalize()` succeeded and `model_store/agents/base_models/current` resolves correctly.

2) Add model metadata & manifest
   - For the base version, add metadata file `{version}/manifest.json` including fields: `approx_vram_mb`, `quantized_variants` (list), `peft_support: true`, `recommended_use_cases` (e.g., generation, reasoning).  Rough starting values:
     - approx_vram_mb: 12200
     - quantized_variants: ["int8_bnb"]
     - peft_support: true

3) Make quantized variants if possible (optional but recommended)
   - Optionally prepare pre-quantized versions for the target CUDA / bnb configuration (exported artifact or alternate snapshot path). This will avoid slow downloads and reduce runtime compilation issues.

4) Publish initial adapters placeholders
   - For agents you plan to adapt first (synthesizer, re-ranker, journalist), stage and finalize a release with an adapter directory populated (e.g., LoRA adapter files or a small stub). `scripts/publish_hf_to_model_store.py` can be called with adapter directories after training in Phase 2.

Phase 2 — Adapter training & storage pipeline
----------------------------------------------
Goal: produce small PEFT adapter artifacts per agent and store them in ModelStore.

Steps:
1) Add training templates and reproducible QLoRA/LoRA pipelines
   - Expand `scripts/train_qlora.py` with explicit adapter outputs, a reproducible training config template, `--agent` and `--adapter-name` flags, plus a `--publish` flag to push to ModelStore automatically after training.
   - Ensure safe defaults for RTX 3090 (batch sizes, gradient checkpointing, BF16/FP16 usage where appropriate).
   - Add a `train_qlora/README.md` linking to recommended training heuristics and sample commands.

2) Example adapter training flow (synthesizer)
   - Run a QLoRA script using a curated fine-tuning dataset for the synthesizer agent:
     ```bash
     conda run -n justnews-py312 python scripts/train_qlora.py --model_name mistralai/Mistral-7B-Instruct --output_dir output/adapters/mistral_synth_v1 --adapter_name mistral_synth_v1 --train_files data/synth_finetune.jsonl --epochs 3 --batch_size 4 --dry-run=0
     ```
   - After validation, publish adapter artifacts to ModelStore:
     ```bash
     python scripts/publish_hf_to_model_store.py --agent synthesizer --model <base-model> --version v20251123-mistral-synth-v1 --model output/adapters/mistral_synth_v1
     ```

3) QA & validation
   - Add unit tests that load adapter via `PeftModel.from_pretrained()` against the base model using `RE_RANKER_TEST_MODE` toggles for CI.
   - Add a sample inference script to smoke‑test that base + adapter load and produce plausible outputs.

Phase 3 — Orchestrator + agent integration
-------------------------------------------
Goal: make the orchestrator, agents, and ModelLoader handle Mistral + adapters cleanly and enable warm pools.

Steps:
1) ModelStore metadata support in orchestrator
   - Extend `agents/gpu_orchestrator/gpu_orchestrator_engine.py` to read ModelStore metadata files when preloading models. The engine should look for per-model `manifest.json` with `approx_vram_mb` and `quantized_variants`.
   - Use metadata to decide whether to preload `int8_bnb` variant or fallback to `device_map='auto'` float16.

2) AGENT_MODEL_MAP.json & AGENT_MODEL_RECOMMENDED.json
   - Create or augment `AGENT_MODEL_MAP.json` entries for agents migrating to mistral + adapter. A recommended schema:
     ```json
     {
       "synthesizer": [{"base":"base_models/models--mistralai--Mistral-7B-v0.3","adapters":["adapters/mistral_synth_v1"]}],
       "re_ranker": [{"base":"base_models/...","adapters":["adapters/mistral_re_ranker_v1"]}]
     }
     ```
   - Add recommended set into `AGENT_MODEL_RECOMMENDED.json` (was already present for non-LLM models). Ensure the orchestrator and `agents/common/model_loader.py` use `AGENT_MODEL_MAP.json` first.

3) Agent code changes
   - Update agent model-loading code to prefer ModelStore paths when available:
     - `agents/common/model_loader.py` already resolves ModelStore paths; ensure adapters are loadable: add function `load_with_adapter(base_model, adapter_path)` that returns a PeftModel-wrapped model.
   - Update specific agents to support causal prompt wrappers vs seq2seq where necessary:
     - `agents/synthesizer/` — add option to route generation tasks to Mistral (adapter) or keep T5/BART for structured seq2seq tasks. Implement a `synthesizer.choose_model_for_task(task)` helper.
     - `agents/reasoning/` — prefer Mistral for chain-of-thought tasks.
     - `agents/critic/`, `agents/fact_checker/` — when generation is needed, load Mistral adapter; for embeddings, keep current small models.

4) Warm pool & adapter hot-swap
   - Ensure `gpu_orchestrator_engine` worker pool loaders use both base and adapter loading sequence (AutoModelForCausalLM.from_pretrained + PeftModel.from_pretrained).
   - Add an orchestrator API to request a pool with `model_id` and `adapter_id` and a hot-swap endpoint already exists (`/workers/pool/{pool_id}/swap`) — test to ensure adapter swapping flows cover Mistral adapter sizes and start/stop logic.

5) Orchestrator policy updates
   - Add `model_vram` and `quantized_variants` values into per-agent metadata and make policy consideration: e.g., prefer int8 variants when `allow_quantized=true`.
   - Update `get_pool_policy`/`_pool_policy_defaults` or add `model_vram_lookup` function so orchestration avoids overcommitting.

Phase 4 — Testing, perf tuning & rollout
----------------------------------------
1) Perf runs and warm pool sizing
   - Use `scripts/perf/simulate_concurrent_inference.py` and `scripts/ops/adapter_worker_pool.py` to run sweeps on production-like GPU nodes. Save standard CSVs for reproducibility in `scripts/perf/results`.
   - Use those sweep results to pick safe defaults: for RTX 3090 with Mistral int8 choose warm pool size 1–2 per GPU for low-latency agents; or a higher pool for non‑latency batch jobs.

2) Health checks & tests
   - Add CI tests that exercise `RE_RANKER_TEST_MODE=1` paths to ensure loading adapters falls back to stub in CI.
   - Add a smoke test that confirms `ModelStore` can be read and that a sample base+adapter load works in dry-run mode (DRY_RUN=1) without actually hitting remote downloads.

3) Canary rollouts
   - Roll out Mistral+adapter to a limited set of hosts / agents: start with `re-ranker` and `synthesizer` on a single GPU node, run steady-state traffic simulation, verify memory/p95 and error rates.
   - Deploy broader progressively to journalist, chief_editor. Keep ability to fallback to `AGENT_MODEL_RECOMMENDED.json` or previous model for critical agents if issues arise.

Phase 5 — CI, monitoring & maintenance
--------------------------------------
1) CI & validation
   - Add a pipeline job to validate ModelStore snapshots: `scripts/check_model_store.py` that ensures `manifest.json` presence, `approx_vram_mb` within reasonable bounds and optionally checks an adapter can be loaded in DRY_RUN.
   - Add pre-commit checks and CI rule to reject accidental commits of large model artifacts (binaries). Your repo already ignores `artifacts/` and added some protections; expand CI to detect tracked large files.

2) Observability & alerts
   - Add orchestrator Prometheus metrics and alerts for OOM events, `worker_pool_evictions`, `model_preload_failures`, high p95 latency, and adapter hot-swap failures. Build dashboards in `monitoring/dashboards`.

3) Operational runbook
   - Add `docs/ops/mistral_rollout_runbook.md` with commands, troubleshooting steps (e.g., bitsandbytes compile troubleshooting), emergency rollback steps, and how to restore the previous model set quickly from ModelStore or HF.

4) Backup and store management
   - Add periodic backups for ModelStore (S3/remote storage) and a rotation policy. The repo already includes `models/model_store_guide.md`; add Mistral-specific notes including expected large weight sizes and backup cadence.

Fallback / rollback plans
-------------------------
- Any agent should be able to fall back to a prior model defined in `AGENT_MODEL_MAP.json` or `AGENT_MODEL_RECOMMENDED.json` if `STRICT_MODEL_STORE` or load fails.
- Default to test stub (`RE_RANKER_TEST_MODE`) in CI.

Timeline & milestones (example)
--------------------------------
- Week 1: Phase 0 + Phase 1 (model selection, ModelStore base publish, manifest). Validate on 1 GPU node.
- Week 2: Phase 2 (train synthesizer + re-ranker adapters; publish to ModelStore). Add tests & CI dry-run.
- Week 3: Phase 3 (agent & orchestrator changes + hot-swap testing). Canary to small host group.
- Week 4: Phase 4 & 5 (perf tuning, full rollout, CI + monitoring finalized).

Files and repo places to change (detailed)
----------------------------------------
- `scripts/publish_hf_to_model_store.py` — use to publish base & adapter snapshots.
- `agents/common/model_store.py` — used for atomic staging/finalize; add expected adapter manifest schema and validation helpers.
- `agents/common/model_loader.py` — extend to expose `load_transformers_with_adapter(base, adapter)` and handle strict ModelStore errors.
- `agents/gpu_orchestrator/gpu_orchestrator_engine.py` — read model manifest, use `approx_vram_mb`, prefer quantized variants and enforce pool policy.
- `AGENT_MODEL_MAP.json` / `AGENT_MODEL_RECOMMENDED.json` — create/extend with Mistral entries, base + adapters, and recommended variants.
- `scripts/train_qlora.py` — add flags and ModelStore publish option.
- `scripts/ops/adapter_worker_pool.py` & `scripts/perf/*` — adopt Mistral-based tests and add a `--adapter` CLI option (already present) and a `--variant` selection (int8 vs fp16).
- Add CI tests in `tests/*` and `pytest.ini` to include ModelStore DRY_RUN validation.
- Add new docs: `docs/model_refactor.md` (this file), `docs/ops/mistral_rollout_runbook.md`, and update `docs/embed_model_assess.md` / `docs/mistral_adapter_rollout.md` with final steps.

Risks & mitigations
---------------------
- CPU/gpu OOMs and mismatched bitsandbytes binary → Mitigate by adding preflight checks and pre-compiled binaries early, and provide fallback to float16/auto device_map.
- Model license / legal concerns → verify HF model card and team legal approval; keep alternate candidate models (MPT, Pythia) in case of restrictions.
- Runbook complexity (hot-swap failure) → keep safe rollbacks and default fallbacks in `AGENT_MODEL_MAP.json`.

Acceptance criteria & verification checklist
-------------------------------------------
Before closing migration for a given agent: all of these must be satisfied:
1) Base model & adapter published and verified in ModelStore (manifest present & checksum verified).
2) Agent loads model+adapter successfully on a production node in non-test mode.
3) Orchestrator can preload base+adapter and create warm pools without OOMs for configured pool sizes.
4) CI runs smoke tests in DRY_RUN mode validating models/adapters are present and that base+adapter load path exists.
5) Monitoring captures p95 latency and OOM failures and alerts are configured.

Appendix — short examples / commands
------------------------------------
Publish base:
```bash
MODEL_STORE_ROOT=/opt/justnews/model_store HF_TOKEN=$HF_TOKEN python scripts/publish_hf_to_model_store.py --agent base_models --model mistralai/Mistral-7B-v0.3 --version v20251123
```

Train adapter (example):
```bash
conda activate justnews-py312
python scripts/train_qlora.py --model_name_or_path mistralai/Mistral-7B-Instruct --output_dir output/adapters/mistral_synth_v1 --train_files data/synth_finetune.jsonl --adapter_name mistral_synth_v1 --epochs 3
```

Publish adapter:
```bash
python scripts/publish_hf_to_model_store.py --agent synthesizer --model mistralai/Mistral-7B-v0.3 --version v20251123-mistral-synth-v1 --model output/adapters/mistral_synth_v1
```

Warm pool test:
```bash
RE_RANKER_TEST_MODE=0 RE_RANKER_MODEL=mistralai/Mistral-7B-v0.3 python scripts/perf/simulate_concurrent_inference.py --workers 3 --requests 30
```

---

If you'd like, my immediate next actions are:
- A) Publish a canonical Mistral‑7B base into ModelStore on the host (requires HF token / permission), then create adapter stubs for `synthesizer` and `re_ranker` and add AGENT_MODEL_MAP.json entries; or
- B) Implement ModelStore metadata support in the Orchestrator and wiring to prefer quantized variants; or
- C) Add the adapter training + publish CI pipeline and a dry-run test harness.

Pick the next action and I’ll continue — I can implement any of the three detailed options.
