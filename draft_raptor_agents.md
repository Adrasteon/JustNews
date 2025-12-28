# Draft Raptor Agents Inventory

This document summarizes each agent in the `agents/` directory, the agent's intended function, key responsibilities, and
current stage of development based on code inspection.

Notes on methodology:

- I inspected `main.py`,`*_engine.py`,`README.md` and other files to determine functionality and maturity.

- "Stage" definitions used below:

- Production (Core): Complete, integrated, robust endpoints and lifecycle, used in production/deployments

- Production (Partial): Substantial but some optional dependencies or features require additional setup

- Experimental: Feature-rich implementation but not yet produced with full integration or tests

- Utility/Library: Helper modules providing shared logic not intended as a standalone agent

- Stub/Scaffold: Minimal or stubbed to make the agent work in restricted envs

---

## Agents

### analyst

- Location: `agents/analyst`

- Function: Quantitative news analysis including NER, sentiment/bias detection, statistical insights, and trend analysis.

- Key files: `analyst_engine.py`,`gpu_analyst.py`(GPU helper),`main.py` (FastAPI)

- Dependencies: spaCy, transformers, torch

- Stage: Production (Core) — Implements many features, GPU logic, and fallback paths. Ready for integration.

- Notes: Uses `cardiffnlp/twitter-roberta-base` for sentiment; supports GPU orchestrator integration for heavy workloads.

### analytics

- Location: `agents/analytics`

- Function: System-wide analytics, advanced performance monitoring, health metrics, and dashboard integration.

- Key files: `analytics_engine.py`,`main.py`,`tools.py`

- Stage: Production (Core) — Wraps centralized analytics engine with background processing and health checks.

- Notes: Integrates with a central `AdvancedAnalyticsEngine`in`agents.common`.

### archive

- Location: `agents/archive`

- Function: Article archiving, retrieval, search and knowledge graph (KG) operations, including `archive_storage` management.

- Key files: `archive_engine.py`,`archive_manager.py`,`main.py`

- Stage: Production (Core) — Feature-rich with KG integration, search and retrieval endpoints.

### auth

- Location: `agents/auth`

- Function: Authentication service (JWT, RBAC), session management; used to secure endpoints and provide user access control.

- Key files: `auth_engine.py`,`main.py`

- Stage: Production (Core)

- Notes: Exposes standard endpoints and integrates with `common.auth_api`.

### c4ai

- Location: `agents/c4ai`

- Function: Crawl4AI HTTP bridge for local use; `server.py`provides`/crawl`and`health`endpoints and bridges to`crawl4ai` package.

- Key files: `server.py`,`bridge.py`

- Stage: Production (Partial) — Works as a bridge but depends on `crawl4ai` external package.

### crawl4ai

- Location: `agents/crawl4ai`

- Function: Helper for starting the Crawl4AI bridge as a `systemd` managed service. Contains README and startup helper.

- Key files: `main.py`,`README.md`

- Stage: Utility/Scaffold — Not a heavy agent, acts as deployment wrapper for `agents/c4ai`.

### crawler

- Location: `agents/crawler`

- Function: Main crawling agent providing robust crawling, extraction, job store, robots parsing, and pipeline integration.

- Key files: `main.py`,`crawler_engine.py`,`extraction.py`,`job_store.py`,`crawler_utils.py`

- Stage: Production (Core) — Implements job persistence, auth, job recovery, robots enforcement, Playwright integration.

- Notes: Includes `crawler_control`and job recovery; integrates with`mcp_bus`and`hitl_service`.

### crawler_control

- Location: `agents/crawler_control`

- Function: Dashboard and control for running, scheduling and monitoring crawls; manages crawl job lifecycle.

- Key files: `main.py`,`crawler_control_engine.py`.

- Stage: Production (Core)

- Notes: Exposes control endpoints and a simple UI for operations.

### critic

- Location: `agents/critic`

- Function: Multi-model editorial critique and content assessment; quality, bias, readability, plagiarism checks.

- Key files: `critic_engine.py`,`main.py`

- Stage: Production (Core) — Implements a multi-model workflow; uses GPU / torch.

### dashboard

- Location: `agents/dashboard`

- Function: Web dashboard, transparency, and monitoring UI; agent management and GPU monitoring.

- Key files: `dashboard_engine.py`,`main.py`,`search_api.py`,`transparency_router.py`

- Stage: Production (Core) — Serves the dashboard and public API.

### fact_checker

- Location: `agents/fact_checker`

- Function: Fact checking and source credibility analysis, LLM-based verification tools.

- Key files: `main.py`,`tools.py`

- Stage: Production (Core) — Implements extensive fact-check tools and endpoints.

### gpu_orchestrator

- Location: `agents/gpu_orchestrator`

- Function: Centralized GPU orchestration, leases, model preloading, MPS management and metrics.

- Key files: `gpu_orchestrator_engine.py`,`main.py`

- Stage: Production (Core) — Robust orchestrator capable of preloading models and managing leases.

- Notes: Integrates `mps_allocation_config.json` and NVML probes; policy based.

### hitl_service

- Location: `agents/hitl_service`

- Function: Human-in-the-loop labeling funnel for candidates, QA, and forwarding ingestion actions.

- Key files: `app.py`,`migrations/001_initial.sql`

- Stage: Production (Core) — Implements candidate queue and forwarding mechanisms, with SQLite for QA staging.

### journalist

- Location: `agents/journalist`

- Function: Crawl4AI-backed discovery and article analysis — wrapper for Crawl4AI for publishing & reading.

- Key files: `journalist_engine.py`,`main.py`

- Stage: Production (Partial) — Lightweight agent that delegates heavy tasks to the `crawl4ai` service; used in publishing flows.

### mcp_bus

- Location: `agents/mcp_bus`

- Function: Inter-agent message bus (Model Context Protocol) and discovery mechanism for agent capabilities; central service.

- Key files: `main.py`,`mcp_bus_engine.py`

- Stage: Production (Core) — Critical for agent discovery and tool invocation.

### memory

- Location: `agents/memory`

- Function: Article ingestion, embedding generation, vector store, and structured persistence.

- Key files: `main.py`,`memory_engine.py`,`vector_engine.py`,`tools.py`

- Stage: Production (Core) — Ingests to MariaDB and Chroma; robust ingestion pipeline.

- Notes: `save_article` persists to DB and vector store, emits metrics, integrates with training data collection.

### newsreader

- Location: `agents/newsreader`

- Function: Vision-Language (LLaVA) - screenshot-based webpage processing; multimodal extraction.

- Key files: `newsreader_engine.py`,`main.py`

- Stage: Production (Partial) — Heavy LLM model usage (LLaVA); MPS/Orchestrator integration required.

### nucleoid_repo

- Location: `agents/nucleoid_repo`

- Function: External 3rd-party node-based repository; included for integration with `reasoning`.

- Key files: JavaScript/TypeScript; not a direct Python agent.

- Stage: Utility/External — Not a core Python agent; included as a library.

### reasoning

- Location: `agents/reasoning`

- Function: Symbolic reasoning with Nucleoid; rule-based & symbolic reasoning for contradictions & explainability.

- Key files: `reasoning_engine.py`,`main.py`

- Stage: Production (Partial) — Provides domain rules & symbolic reasoning; integrates with `nucleoid_repo` for advanced features.

### scout

- Location: `agents/scout`

- Function: Content discovery, site crawling and initial classification (BERT/DeBERTa / RoBERTa usage), integrative with Crawl4AI.

- Key files: `scout_engine.py`,`main.py`,`crawl4ai_server_impl.py`

- Stage: Production (Core) — Solid implementation for discovery; uses GPU optional logic and pipelines.

### sites

- Location: `agents/sites`

- Function: Site-specific crawling logic and helpers (e.g., `bbc_crawler.py`,`generic_site_crawler.py`).

- Key files: `generic_site_crawler.py`,`bbc_crawler.py`

- Stage: Production (Partial) — Specific site implementations and stubs for fetchers.

### synthesizer

- Location: `agents/synthesizer`

- Function: Synthesis, summarization, neutralization and cluster-based aggregation using BART/FLAN-T5 and embedding models; also BERTopic clustering.

- Key files: `synthesizer_engine.py`,`main.py`

- Stage: Production (Core) — Implements clustering, generation, and neutralization pipelines; GPU-aware.

---

## Overall Remarks & Next Actions

- Most major agents (crawler, memory, mcp_bus, gpu_orch, archive, hitl_service, chief_editor, analyzer, synthesizer) are production-ready and show robust implementation and integrations.

- Heavy LLM-based agents (synthesizer, newsreader, some parts of analyst, critic, chief_editor) rely on GPU orchestration and quantization strategies — recommended to add per-model VRAM metadata and to use quantization by default when needed.

- `nucleoid_repo`is not a direct Python agent — it’s a referenced external package used by`reasoning` and may be maintained separately.

- Next: Create an integration matrix documenting dependencies between agents and ensure `model_store`mapping in`AGENT_MODEL_MAP.json`is aligned with recommendations in`AGENT_MODEL_RECOMMENDED.json`.

---

If you want, I can:

- Produce a dependency graph showing agent interactions.

- Propose a CI plan to run in-process integration tests for each agent combination.

- Start a PR to add `AGENT_MODEL_RECOMMENDED.json`into`AGENT_MODEL_MAP.json` as a validated default set.

Which would you like me to do next?
