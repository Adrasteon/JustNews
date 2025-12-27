# Article Processing Paths

Based on the tests and workflow verified on 2025-11-14.

## Article Processing Paths

### Path 1: Direct Crawler Ingestion (Pre-HITL, Legacy)

1. **Crawler** fetches article from source site

1. **Crawler** validates and extracts content

1. **Crawler** calls `_ingest_articles()`

1. Article stored in production database (MariaDB + ChromaDB for embeddings)

1. Article marked as `ingested` or `duplicate`

### Path 2: HITL-Assisted Ingestion (Current Implementation)

1. **Crawler** fetches article from source site

1. **Crawler** builds HITL candidate payload:

   - Converts `site_id` from int to string

   - Includes `extracted_text`, `extracted_title`, `url`

   - Adds `features` (word_count, confidence, paywall_flag, language)

   - Attaches `raw_html_ref` for archive storage

1. **Crawler** POSTs candidate to `http://127.0.0.1:8040/api/candidates`

1. **HITL Service** receives candidate:

   - Stores in `hitl_staging.db` → `hitl_candidates` table

   - Sets status to `pending`

   - Optionally forwards to `HITL_CANDIDATE_FORWARD_AGENT` (if configured)

1. **HITL Service** serves candidate via `/api/next`:

   - Prioritizes by `HITL_PRIORITY_SITES` if configured

   - Returns batch to UI or API consumer

   - Marks as `in_review` when fetched

1. **Annotator** (human or automated) labels via `/api/label`:

   - Submits: `candidate_id`, `label` (valid_news/messy_news/not_news), `cleaned_text`, `annotator_id`

1. **HITL Service** processes label:

   - Stores in `hitl_labels` table with `label_id`

   - Builds `ingest_payload` with full candidate data + label

   - Builds `training_payload` for ML system

   - Optionally samples for QA queue (~10% rate)

1. **HITL Service** dispatches asynchronously:

    - **Ingest Forward** (if `HITL_FORWARD_AGENT`/`_TOOL` set):

       - Calls MCP Bus: `POST /call` → `{agent: "archive", tool: "queue_article", payload: ingest_payload}`

       - Retries 3x with exponential backoff on failure

       - Updates `ingestion_status`: `pending` → `enqueued` (success) or `error` (failure)

   - **Training Forward** (if `HITL_TRAINING_FORWARD_AGENT`/`_TOOL` set):

     - Calls MCP Bus → training system

     - Payload includes label + candidate for model retraining

   - Both forwards happen in parallel via `asyncio.create_task()`

1. **Archive Agent**:

   - Receives `ingest_payload` via MCP Bus using the `queue_article` tool

   - Normalizes metadata (url hashing, canonicalization, annotator context)

   - Verifies / copies `raw_html_ref` artefacts into `archive_storage/raw_html` and emits `raw_html_*` counters

   - Stores article + embeddings via `agents.memory.tools.save_article` (MariaDB + ChromaDB)

   - Emits `ingest_success_total` / `ingest_latency_seconds` metrics and reports duplicates (dashboard wiring next)

### Path 3: Training Feedback Loop

1. **HITL Service** sends `training_payload` to **Training System**

1. **Training System** (when implemented):

   - Receives labeled examples

   - Updates models (classification, extraction, etc.)

   - Increments `justnews_training_examples_total{example_type="hitl_label"}`

1. **GPU Orchestrator** manages model deployment:

   - New models pushed to `model_store/`

   - Agents reload models on next inference request

### Path 4: QA Review (Sampled)

1. **HITL Service** randomly samples ~10% of labels into `hitl_qa_queue`

1. **QA Reviewer** calls `/api/qa/list` to fetch samples

1. **QA Reviewer** submits review via `/api/qa/review`:

   - `status`: `pass` or `fail`

   - `notes`: optional feedback

1. Failed QA items trigger alerts if failure rate exceeds threshold

## Key Databases & Storage

- **`hitl_staging.db`** (SQLite):

  - `hitl_candidates`: incoming articles awaiting labels

  - `hitl_labels`: human annotations with metadata

  - `hitl_qa_queue`: sampled labels for quality review

- **MariaDB** (Primary structured storage):

  - Article metadata (title, URL, source_id, timestamps)

  - **Clean article content**: main/body text (from `cleaned_text` in label payload)

  - Duplicate detection via normalized URLs

  - Relational data (sources, crawl jobs, ingestion status)

- **ChromaDB** (Vector database, port 3307):

  - Article embeddings for semantic search

  - Collection: `articles`

  - Enables similarity matching and content discovery

- **Archive Storage** (filesystem):

  - `archive_storage/raw_html/`: original HTML for transparency

  - `archive_storage/transparency/`: audit trails

- **Model Store** (filesystem):

  - `model_store/<agent>/`: per-agent model weights

  - Managed by GPU Orchestrator

## Current Status (Verified 2025-11-14)

- ✅ Crawler → HITL candidate submission

- ✅ HITL candidate storage

- ✅ Label API and storage

- ✅ Stats tracking

- ✅ Payload construction (ingest + training)

- ✅ MCP Bus dispatch attempt

- ✅ Archive ingest wiring (`archive.queue_article`, Stage B tests)

- ⏸️ Training system integration (awaiting implementation)
