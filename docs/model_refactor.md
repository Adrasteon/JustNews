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
   - `agents/reasoning/`, `agents/critic/`, `agents/hitl_service/` — reasoning & HITL interactions; Critic now ships with the `mistral_critic_v1` adapter for higher-accuracy editorial gating while retaining lightweight fallback tools for outage scenarios.
   - `agents/fact_checker/` — accuracy-critical claim verification now uses the shared Mistral base via the `mistral_fact_checker_v1` adapter for long-form evidence synthesis; retrieval/semantic search continues to rely on mpnet-sized encoders.
   - `agents/analyst/` — bias/sentiment/persuasion scoring now prioritizes accuracy over latency, so add a Mistral adapter-powered tool alongside existing RoBERTa fallbacks.
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
- Per-agent adapter artifacts (LoRA/QLoRA) produced and published in ModelStore for: synthesizer, re-ranker, journalist, chief_editor, reasoning, and analyst agents (analyst retains legacy RoBERTa tooling as a fallback but defaults to the new Mistral adapter for production decisions).
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
   - Canonical checkpoint + license are now pinned to `mistralai/Mistral-7B-Instruct-v0.3` (Apache-2.0). Reference metadata lives in `models/metadata/mistral-7b-instruct-v0.3.json` for downstream tooling.

2) Host readiness checklist
   - Confirm that GPU nodes have required CUDA + drivers and that bitsandbytes native binaries are built against target CUDA (documented in repo). Add an automated verification script for `bitsandbytes` compatibility in `infrastructure/systemd/preflight.sh` or a new preflight utility.
   - Confirm `MODEL_STORE_ROOT` is available and writable on target nodes; ensure backup & snapshot cadence is documented.

3) Repo & QA housekeeping
   - `AGENT_MODEL_MAP.json` now exists and seeds entries for `synthesizer` + `re_ranker` agents pointing at the canonical base and placeholder adapter slots. Continue extending it for journalist, chief_editor, reasoning, **and analyst** so all critical decision-makers pull from the shared base.
   - Add a `docs/mistral_adapter_rollout.md` -> already present; augment with an entry describing canonical base + adapter naming conventions.

Phase 1 — ModelStore publishing
--------------------------------
Goal: publish canonical Mistral base weights and a canonical path / layout in ModelStore.

Steps:
1) Create a canonical ModelStore version for the Mistral base
    - ✅ Completed: published `mistralai/Mistral-7B-Instruct-v0.3` as `base_models/versions/v20251123-mistral-v0.3` using the metadata-aware script. All GPU hosts should replicate this command:
       ```bash
       MODEL_STORE_ROOT=/opt/justnews/model_store HF_TOKEN=$HF_TOKEN \
          python scripts/publish_hf_to_model_store.py \
             --agent base_models \
             --model mistralai/Mistral-7B-Instruct-v0.3 \
             --version v20251123-mistral-v0.3 \
             --metadata models/metadata/mistral-7b-instruct-v0.3.json
       ```
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
----------------------------------------------
Goal: produce small PEFT adapter artifacts per agent and store them in ModelStore.

Steps:
1) Add training templates and reproducible QLoRA/LoRA pipelines
   - ✅ `scripts/train_qlora.py` now exposes `--agent`, `--adapter-name`, `--adapter-version`, `--train-files`, hyper-parameter knobs, and `--publish` to push adapters directly into ModelStore. It saves `training_summary.json` alongside the adapter payload for auditing.
   - Defaults target RTX 3090 int8/4bit configs (LoRA r=64, alpha=16, gradient checkpointing optional). Review `--max-train-samples` + `--dry-run` for CI-safe smoke tests.
   - See `train_qlora/README.md` for usage recipes, dependency notes, and publishing flow.

2) Example adapter training flow (synthesizer)
    - Run a QLoRA script using a curated fine-tuning dataset for the synthesizer agent (adjust dataset + hyper-params as needed):
       ```bash
       MODEL_STORE_ROOT=/opt/justnews/model_store \
       conda run -n justnews-py312 python scripts/train_qlora.py \
          --agent synthesizer \
          --adapter-name mistral_synth_v1 \
          --model_name_or_path mistralai/Mistral-7B-Instruct-v0.3 \
          --train-files data/synth_finetune.jsonl \
          --output_dir output/adapters/mistral_synth_v1 \
          --epochs 3 \
          --train-batch-size 1 \
          --gradient-accumulation 8 \
          --publish
       ```
    - The `--publish` flag now copies `output/adapters/mistral_synth_v1` into the `synthesizer` ModelStore namespace and writes adapter metadata into the manifest. Use `--adapter-version` when you need a deterministic version tag; otherwise the script timestamps it automatically.

3) QA & validation
   - Add unit tests that load adapter via `PeftModel.from_pretrained()` against the base model using `RE_RANKER_TEST_MODE` toggles for CI.
   - Add a sample inference script to smoke‑test that base + adapter load and produce plausible outputs.

Phase 3 — Orchestrator + agent integration
-------------------------------------------
Goal: make the orchestrator, agents, and ModelLoader handle Mistral + adapters cleanly and enable warm pools.

Steps:
1) ModelStore metadata support in orchestrator
   - ✅ `agents/gpu_orchestrator/gpu_orchestrator_engine.py` now parses `AGENT_MODEL_MAP.json`, resolves each entry's manifest via `agents/common/model_loader.get_agent_model_metadata`, and tracks the metadata (approx_vram_mb, quantized_variants) when kicking off preload jobs. This ensures the orchestration layer knows exactly which base snapshot + adapter paths exist before provisioning pools.
   - Next: plug the captured metadata into pool sizing logic so we automatically pick `bnb-int8` vs `fp16` variants when enforcing policies.

2) AGENT_MODEL_MAP.json & AGENT_MODEL_RECOMMENDED.json
   - ✅ `AGENT_MODEL_MAP.json` now drives both loader and orchestrator. `agents/common/model_loader.py` resolves base + adapter locations (including ModelStore versions) and exposes `load_transformers_with_adapter()` plus a metadata helper for consumers. The orchestrator consumes the same map when preloading entries, ensuring one source of truth for base/adapters.
   - Continue extending the map for journalist/chief_editor as adapters come online; update `AGENT_MODEL_RECOMMENDED.json` once we have production-ready versions for those agents.
     ```json
     {
       "synthesizer": [{"base":"base_models/models--mistralai--Mistral-7B-v0.3","adapters":["adapters/mistral_synth_v1"]}],
       "re_ranker": [{"base":"base_models/...","adapters":["adapters/mistral_re_ranker_v1"]}]
     }
     ```
   - Add recommended set into `AGENT_MODEL_RECOMMENDED.json` (was already present for non-LLM models). Ensure the orchestrator and `agents/common/model_loader.py` use `AGENT_MODEL_MAP.json` first.
    - ✅ Fact Checker and Critic now ship with canonical entries: `fact_checker/adapters/mistral_fact_checker_v1` and `critic/adapters/mistral_critic_v1` are published to ModelStore and referenced directly in `AGENT_MODEL_MAP.json`. Retrieval-only fallbacks remain listed in `AGENT_MODEL_RECOMMENDED.json` until we migrate those pieces to adapter-aware flows.

3) Agent code changes
   - `agents/common/model_loader.py` now provides `load_transformers_with_adapter()` plus `get_agent_model_metadata()` so agents can request the canonical base+adapter combo defined in the map. Next step is wiring individual agents (`synthesizer`, `re_ranker`, etc.) to call these helpers.
   - Update specific agents to support causal prompt wrappers vs seq2seq where necessary:
     - `agents/synthesizer/` — add option to route generation tasks to Mistral (adapter) or keep T5/BART for structured seq2seq tasks. Implement a `synthesizer.choose_model_for_task(task)` helper.
     - `agents/reasoning/` — prefer Mistral for chain-of-thought tasks.
       - `agents/analyst/` — add a high-accuracy Mistral adapter tool for sentiment/bias/persuasion scoring, keeping the RoBERTa pipelines as low-resource fallback paths but defaulting to the adapter for production flows.
       - ✅ `agents/critic/` and `agents/fact_checker/` now default to their adapters (`mistral_critic_v1` and `mistral_fact_checker_v1`) for long-form judgments, while evidence retrieval continues to rely on small sentence-transformer models.
    - Adapter coverage checklist for these accuracy-critical agents:
       - Fact Checker smoke tests now cover the adapter load path via `tests/agents/test_fact_checker.py` with `RE_RANKER_TEST_MODE=1`, ensuring prompt formatting and retrieval fallbacks behave in CI.
       - Critic regression harness exercises `agents/critic/critic_engine.py` through the shared loader helper so the orchestrator preloads the adapter before policy checks execute.
       - ModelStore publishes a `training_summary.json` for each adapter so we can trace provenance when comparing to the legacy DistilRoBERTa/Flan flows.

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
