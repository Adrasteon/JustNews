# JustNews Agent Development Plan & System Audit

**Date:** January 14, 2026
**Status:** Architecture Refinement Strategy

## 1. Executive Summary
The system audit reveals a tension between two architectural goals: **Independent Agent Evolution** (supported by the `training_system`) and **Resource Efficiency**.

Currently, agents achieve independence by duplicating heavy resources: `FactChecker`, `Scout`, and `Analyst` all load separate instances of BERT/RoBERTa models to fine-tune them for their specific tasks. This leads to massive RAM waste and eventual OOM crash.

**The Strategic Pivot:**
Instead of consolidating agents into a generic "Inference Service" (which loses the specialized training), we will expand the **"Base Model + Adapter"** pattern—currently used for Mistral—to the *entire* model stack (BERT, RoBERTa, etc.).

**Target Architecture:**
*   **LLM Layer (Generative):** Single `vLLM` instance hosting Mistral 7B + Per-Agent Adapters (Current State).
*   **Encoder Layer (Discriminative):** Single `EncoderService` hosting 1 instance of `roberta-base` and 1 instance of `bert-base`. Agents load their specific **LoRA Adapters** (2-10MB) into this shared host for tasks like Sentiment, NER, and Fact Verification.

---

## 2. Per-Agent Analysis & Adapter Strategy

### **1. Crawler (`agents/crawler/`)**
*   **Role**: Orchestrates fetching.
*   **Status**: **Primary Ingress Agent**.
*   **Action**: Consolidate all crawling logic here. Absorb any unique discovery logic from `Scout`.
*   **Training Needs**: Minimal (Reinforcement Learning for crawl scheduling potentially - future scope).

### **2. Scout (`agents/scout/`)**
*   **Current State**: Structurally redundant "Smart Crawler" that loads heavy models.
*   **Refined Plan**: **REPURPOSE as "Research Agent" (The Librarian)**.
    *   **New Role**: "Targeted Data Gatherer" for the Fact Checker.
    *   **Logic Change**:
        *   **Remove**: All local crawling and heavy analysis models (BERT/RoBERTa).
        *   **Add**: Search Engine Integration (Google/Bing/DuckDuckGo API) and Query Generation logic.
    *   **Workflow**:
        1.  `FactChecker` sends a claim (e.g., "Inflation rose 5%").
        2.  `Scout` generates queries (e.g., "US inflation rate 2025 statistics").
        3.  `Scout` calls `Crawler` to fetch top hits.
        4.  `Scout` filters for relevance and returns "Evidence Pack" to `FactChecker`.
    *   **Benefit**: Separates "Broad Discovery" (Crawler) from "Targeted Verification" (Scout).

### **3. Analyst (`agents/analyst/`)**
*   **Current State**: Loads `spaCy` (large) and `toxic-bert` (redundant).
*   **Refined Plan**:
    *   **NER**: Migrate from `spaCy` transformer models to a **BERT-NER Adapter** on the shared service.
    *   **Sentiment**: Use an **Analyst-Sentiment Adapter** on the shared `roberta-base`.

### **4. Fact Checker (`agents/fact_checker/`)**
*   **Critique**: Currently trains a *Sentiment* model (`sst-2`) for *Fact Checking*.
*   **Refined Plan**:
    *   **Architecture**: Switch to NLI (Natural Language Inference).
    *   **Training**: Train a **Fact-Checker-NLI Adapter** (on `roberta-base`) using the `training_system`.
    *   **Benefit**: The agent "owns" the weights (the adapter) but shares the heavy compute (the base model).

### **5. Chief Editor (`agents/chief_editor/`)**
*   **Current State**: Loads 5 separate pipelines.
*   **Refined Plan**:
    *   **Consolidation**: Request inference from the shared `EncoderService` using specific adapters.
    *   **Editorial Voice**: Train a specialized **Editor-Style Adapter** (LoRA on Mistral 7B or Roberta) to enforce the publication's voice and style guide. The `training_system` will fine-tune this adapter on approved articles.

### **6. Synthesizer (`agents/synthesizer/`)**
*   **Current State**: Loads `BART` and `BERTopic`.
*   **Refined Plan**:
    *   **Generative**: Migrate `BART` usage to the **Mistral 7B** instance using a **Synthesizer-Summary Adapter**. This removes `BART` from memory entirely.
    *   **Clustering**: `BERTopic` needs embeddings. Use a shared **Embedding Service** (part of Memory agent) instead of loading a local `sentence-transformers` model.

### **7. HITL & Publisher (`agents/hitl_service`, `agents/publisher`)**
*   **Publisher**: Move to root (`/web_app`).
*   **HITL**: Migrate SQLite to MariaDB to unify the "Training Loop" storage (Feedback goes to DB -> `training_system` consumes DB -> updates Adapters).

---

## 3. Implementation Roadmap

### **Phase 1: Universal Adapter Infrastructure**
1.  **Develop `EncoderService`**:
    *   A FastApi/gRPC service that loads `bert-base-uncased` and `roberta-base`.
    *   API: `infer(text, adapter_id="scout_v1")`.
    *   Backend: Uses `peft` library to dynamically swap LoRA weights on the frozen base model.
2.  **Update `binding_spec`**:
    *   Define standard Adapter Interfaces for non-LLM models.

### **Phase 2: Agent Refactoring**
3.  **Strip & Switch**:
    *   Go through each agent (`Analyst`, `FactChecker`, etc.).
    *   Delete `self.model = AutoModel.from_pretrained(...)`.
    *   Replace with `self.client.classify(text, adapter="fact_checker_v1")`.
4.  **Training System Integration**:
    *   Update `training_coordinator.py` to save checkpoints as **Adapters** (LoRA weights), not full model dumps.

### **Phase 3: Migration**
5.  **Publisher Move**: Relocate the Django app to the root level.
6.  **Database Unification**: Migrate HITL staging data to the primary MariaDB.

This plan resolves the RAM crisis while strictly adhering to the "Per-Agent Training" requirement by using efficient Adapter technology across the entire stack.
