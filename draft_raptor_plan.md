## 2.1 Per-Agent Model Suitability Review (Summary & Recommendations)

- scout

- Current models: `sentence-transformers/all-MiniLM-L6-v2`,`all-mpnet-base-v2`,`paraphrase-multilingual-MiniLM-L12-v2`

- Suitability: Good. Default `all-MiniLM-L6-v2`for embeddings is ideal for resource usage;`mpnet` used as a higher-quality fallback.

- Recommendation: keep current configuration; prefer MiniLM by default, mpnet as optional high-quality path.

- fact_checker

- Current models: `sentence-transformers/all-mpnet-base-v2`,`multi-qa-mpnet-base-dot-v1`,`paraphrase-albert-base-v2`

- Suitability: Good for retrieval and similarity checks. For claim analysis, optionally add a small sequence-model LLM (e.g., `google/flan-t5-small`) and rely on PEFT/LoRA for fine-tuning.

- Recommendation: keep retrieval encoders; add `flan-t5-small` for conditional generation or evidence summarization invoked via GPU Orchestrator.

- memory

- Current models: `sentence-transformers/all-MiniLM-L6-v2` — ideal for embeddings and small footprint.

- Recommendation: keep and document quantized in-memory embeddings if necessary.

- synthesizer

- Current: `distilgpt2`,`google/flan-t5-small`— the repo contains`flan-t5-large`variants in`model_store` (used for batch or high-quality synth).

- Suitability: `flan-t5-small`is acceptable for shorter neutralization & generation tasks;`flan-t5-base`/`large`produce
  higher-quality content but need careful GPU orchestrator scheduling and quantization (use`bitsandbytes` 8-bit or 4-bit
  and PEFT for training).

- Recommendation: Default to `flan-t5-small`unless high-quality mode is explicitly requested; ensure quantized models exist in`model_store`and choose`device_map='auto'`and`load_in_8bit=True` in prod.

- critic, analyst, chief_editor, newsreader  # NOTE: `balancer` removed — responsibilities moved to critic/analytics/gpu_orchestrator

- Current: `sentence-transformers/all-distilroberta-v1`,`all-MiniLM-L6-v2` and other small models.

- Suitability: Good. If the `analyst`requires GPU-based roberta models for high throughput, prefer`distilroberta` variants or quantized models to reduce memory.

- Recommendation: prefer `distil` variants of sentiment/bias models and ensure GPU orchestrator provides proper shares.

- Overall: avoid widespread `flan-t5-large`or`bart-large` defaults unless the orchestrator supports on-demand lease
  scheduling, and the model is quantized (bitsandbytes) and fine-tunable using PEFT/LoRA.

### Quantization & Fine-tuning (PEFT/LoRA) Guidance

- Use `bitsandbytes`to enable 8-bit inference via`load_in_8bit=True`in`transformers` where necessary. Add tests and CI steps to verify quantized performance and numeric parity.

- For training/fine-tuning, prefer PEFT/LoRA and adapters to reduce VRAM and keep models trainable on RTX 3090.

- For large LLMs (T5/BART), prefer `flan-t5-small`/`flan-t5-base`as default; allow`flan-t5-large` only under a GPU lease with quantization and batch scheduling.

- Add `model_store`metadata entries for`quantized_variants`and`peft_support`to`model_store/<agent>/metadata.json`.

### Training Guidance on RTX 3090

- RTX 3090 (24GB VRAM):

- Fine-tune small to medium models such as `flan-t5-small`,`flan-t5-base`(with PEFT) or`distil*` models directly with minimal memory tuning.

- For `flan-t5-large`or`bart-large`, use gradient checkpointing, activation checkpointing, and offloading (`accelerate` CPU offload) and LoRA/PEFT to keep trainable parameters low.

- Encourage LoRA/PEFT on all LLM fine-tuning tasks to keep training affordable and usable on single-GPU.

- When training embedding models (sentence-transformers), use small batch sizes and mixed-precision where possible to fit in VRAM.

### GPU Orchestrator Recommendations for Model VRAM

- Add per-model approximate VRAM values to `mps_allocation_config.json` for accurate scheduling. For example:

- `sentence-transformers/all-MiniLM-L6-v2`: 0.5GB

- `sentence-transformers/all-mpnet-base-v2`: 1.2GB

- `cardiffnlp/twitter-roberta-base-sentiment-latest`: 1.5GB

- `unitary/toxic-bert` (or RoBERTa toxicity): 1.5GB

- `google/flan-t5-small`: 1.8GB (quantized 8-bit: 1.2GB)

- `google/flan-t5-base`: 4.0GB (quantized 8-bit: 2.5GB)

- `google/flan-t5-large`: 11+GB (quantized 8-bit may reduce to 6-8GB; still heavy)

- `facebook/bart-large-cnn`: 3.0GB (quantized 8-bit: ~2.2GB)

- These are approximate values; `gpu_orchestrator` should collect telemetry and refine them.

## 6.1 GPU Orchestrator & Model Preload Policy Recommendation

- Orchestrator `policy`should include model memory estimates for each model in`AGENT_MODEL_MAP.json`for accurate preload
  & allocation.`mps_allocation_config.json` should contain model-level approximate VRAM requirements.

- Orchestrator `policy`should include model memory estimates for each model in`AGENT_MODEL_MAP.json`for accurate preload
  & allocation.`mps_allocation_config.json`should contain model-level approximate VRAM requirements and
  a`model_vram`section or a`model_registry` that maps model_id -> {approx_vram_mb, quantized_variants}.

- Add support to orchestrator to read `model_store`metadata for`approx_vram_mb`and`quantized_variants` to calculate safe allocations.

- Orchestrator: when checking model preload or granting GPU leases, prefer quantized variants if memory is constrained; fallback to CPU-only mode for real-time requests if no GPU support is available.

- Orchestrator should have a 'quality' vs 'latency' preference: 'real-time' uses `default` smaller or quantized models, while 'batch' or 'high-quality' uses larger models when allowed by policy.

- If `STRICT_MODEL_STORE=1`, orchestrator must fail preload if memory can't be met, otherwise fallback to CPU-only mode or smaller quantized models.

- Provide `allowed_variants`per agent
  in`AGENT_MODEL_MAP.json`(e.g.,`flan-t5-small`default,`flan-t5-base`optional,`flan-t5-large`reserved for batch jobs)
  and adjust`mps_allocation_config.json` accordingly.

- Provide `allowed_variants`per agent (see`AGENT_MODEL_RECOMMENDED.json`) and adjust`mps_allocation_config.json`
  accordingly; orchestrator should be able to choose the quantized or base variant based on policy & runtime load.

- [ ] A6: Add quantized/PEFT-ready model variants to `model_store`(e.g., 8-bit`flan-t5-small`or`base`), update`model_store`metadata with`approx_vram_mb`,`quantized_variants`, and`peft_support` flags.

- [ ] A6: Add quantized/PEFT-ready model variants to `model_store`(e.g., 8-bit`flan-t5-small`or`base`),
  update`model_store`metadata with`approx_vram_mb`,`quantized_variants`, and`peft_support`flags, and publish
  an`AGENT_MODEL_RECOMMENDED.json`.

- [ ] B5: Add GPU orchestrator detection of quantized models and allow dynamic selection based on `policy`and`real-time`vs`batch` mode.

- [ ] C4: Add a `model_health`probe that checks quantized model inference parity for each agent in production and populates`gpu_orchestrator` metrics.

# Draft Raptor Plan

This document captures the action plan and task list for the JustNews architecture refinement.

Goals:

- Maintain independent, self-reliant agents: each owns its own LLM model(s) from `model_store`.

- Preserve modularity while adding robust analysis (bias/sentiment/persuasion) and clustering.

- Avoid Docker for orchestration; prefer `systemd` for production and in-process uvicorn for CI/integration tests.

- Add observability, traceability, and migration support.

---

## 1. High-Level Pipeline

1. Crawl → candidate creation (Crawler / Crawl4AI).

1. Extract & normalize (crawler extraction tooling or `journalist` / extraction agent).

1. Store candidate (HITL candidate store and `raw_html_ref`).

1. Memory ingest: store article in MariaDB and compute embeddings; return `ingest_job_id`.

1. Analysis: compute `sentiment`,`bias_vector`,`persuasion_score`.

1. Clustering: compute `cluster_id` and store it with article metadata.

1. HITL flow: label, QA, optional re-ingest forward.

1. Publish/Archive: `journalist`/`archive_agent` publishes and stores archives.

---

## 2. Agent Ownership & Models

- Agents are self-contained FastAPI services run as `systemd` services.

- Each agent loads & owns models (from `model_store`) declared in`AGENT_MODEL_MAP.json`.

- `model_provider`abstraction will be included as`agents/common/model_provider.py` to unify loading, warming, and unloading.

- Optional `model_server` is available as an optimization in constrained environments but is not the default.

---

## 3. New/Enhanced Agents & Responsibilities

- `analysis`agent (`agents/analysis/analysis_engine.py`): centralizes sentiment, bias, persuasion, and clustering.

- Endpoints: `/analyze`(single article),`/analyze/batch`(batch),`/clusters`.

- Output: `analysis_metadata` fields (sentiment, bias_vector, persuasion_score).

- Clustering: incremental or batch clustering (HDBSCAN recommended).

- `memory` agent: limited to ingest & vector store responsibilities: compute embeddings and persist metadata.

- Persists `analysis_metadata`,`cluster_id`,`ingest_job_id`,`crawler_job_id`.

- `HITL`agent: already exists; ensure`ingest_job_id` flows forwards when forking ingestion.

---

## 4. Model Management & Lifecycle

- `model_store`: canonical model versions and metadata.

- `AGENT_MODEL_MAP.json`: validate at agent start; agent will refuse to load models not in the allowed list.

- `Model Provider` will handle:

- Load and warm models based on config; optional device selection (CPU/GPU).

- Hot-swap endpoint for model updates, with safe warm-up sequence.

- Logging `model_version` at inference.

---

## 5. Observability & Traceability

- Trace IDs: `trace_id`or`job_trace`to be propagated across agents via`X-Trace-Id`or`request_id` metadata.

- `job_traces` table schema (MariaDB):

- id (pk), trace_id, job_id, agent, event_type, event_details (JSON), ts

- Logs include `agent`,`model_version`,`trace_id`,`job_id`.

- Metrics added for analysis (sentiment, bias, persuasion), clustering, job fallback & failures.

---

## 6. Security

- Each public endpoint requiring token: `CRAWLER_API_TOKEN`,`HITL_TOKEN`,`ANALYSIS_TOKEN`.

- Tokens rotate via `secret_manager` or a local rotation process.

- Token misuse logs and enforce TL;DR: no anonymous ingestion without token.

---

## 7. Persistence: DB Migrations & Schema Changes

- Add `job_traces`migration SQL in`database/migrations`.

- Add `analysis_metadata`fields and`cluster_id`to`articles.metadata`(json) and to`memory` persistence flows.

- Update `scripts/init_database.py`to include`job_traces`and schema changes for`articles` metadata.

---

## 8. Clustering & Analysis Design

- Clustering component:

- `agents/analysis/clustering.py` will implement cluster routines using Chroma vectors or local scikit-learn/HDBSCAN fallback.

- Clusters store `cluster_id`,`cluster_name`,`coherence_score`.

- Optionally provide cluster-level topic labels (auto-summarized) via LLM summarizer.

- Analysis component:

- `compute_sentiment(text)`: returns numeric score & label (neg/neutral/pos).

- `detect_bias(text, metadata)`: returns a {left, center, right} vector and rationalization fields.

- `persuasion_score(text)`: heuristics or model-based features (counts of emotive words, rhetorical devices, assertive language scores).

---

## 9. Testing & CI (No Docker)

- Integration harness (No Docker): In-process agent start via `uvicorn.run` within pytest with SQLite and in-memory Chroma.

- Tests to add:

- Unit tests for sentiment, bias, persuasion, clustering.

- Integration test for end-to-end `crawl -> memory -> analyze -> cluster -> persist` using local test models.

- CI job `integration-no-docker` to execute integration harness with in-memory stores.

---

## 10. Tasks & Priorities

### Priority (High)

- [ ] A1: Add `analysis`agent (files:`agents/analysis/analysis_engine.py`,`agents/analysis/clustering.py`).

- [ ] A2: Implement `Model Provider`(`agents/common/model_provider.py`).

- [ ] A3: Persist analysis metadata & `cluster_id`in`memory`(`agents/memory/memory_engine.py`,`agents/memory/tools.py`).

- [ ] A4: Add DB migration for `job_traces`and update`scripts/init_database.py`.

- [ ] A5: Propagate `ingest_job_id`and`crawler_job_id`across the pipeline (`hitl_service`,`crawler`,`memory`).

### Priority (Medium)

- [ ] B1: Add test coverage for analysis functions & clustering.

- [ ] B2: Add CI job `integration-no-docker` and in-process harness.

- [ ] B3: Add metrics & alerting rules for analysis & clustering.

- [ ] B4: Implement a lightweight `shared model server` option for resource constrained deploys.

### Priority (Low)

- [ ] C1: Add auto-summarize cluster labels via a `synthesizer` LLM call.

- [ ] C2: Add a nightly batch re-balance job for clusters.

- [ ] C3: Minor documentation updates & runbooks for token rotation and model update steps.

---

## 11. Acceptance Criteria

- The `analysis`agent processes`analyze`requests and returns`analysis_metadata`.

- `articles`metadata contains`analysis_metadata`and`cluster_id` post-ingest.

- Trace and job lifecycle are visible: `job_traces` show a start → running → completed sequence.

- The `integration-no-docker` harness runs and validates the end-to-end flow.

- All tests pass in CI for unit and integration tests.

---

## 12. Next Steps (Recommended)

1. Create `agents/analysis`scaffold with endpoints; add unit tests for`compute_sentiment`,`detect_bias`, and`persuasion_score`.

1. Create `agents/common/model_provider.py`and integrate with`analysis`and`memory` agents.

1. Add DB migration `XXX_job_traces.sql`and update`scripts/init_database.py`.

1. Add unit tests for cluster and integration test that runs the pipeline in-process.

1. Add metrics & detection for system faults.

1. Add `AGENT_MODEL_RECOMMENDED.json` to the repo (covers default & fallback models per-agent) and implement
   orchestrator checks to fall back to quantized variants or CPU-only when GPU resources are insufficient.

1. Implement model metadata additions and a `model_vram`registry in`config/gpu/mps_allocation_config.json` to assist preloading.

1. Add `model_health`probes and a quantized-parity test in CI that uses`bitsandbytes`and`PEFT` wrappers to confirm inference correctness.

---

Thank you — please review this plan and point out any refinements, or select which task to start next.
