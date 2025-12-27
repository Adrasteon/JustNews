# JustNews System Startup Action Plan

**Date**: December 18, 2025 **Objective**: Get JustNews up and running to crawl and fill database(s) with test/training
data

---

## Executive Summary

Based on codebase analysis, JustNews has **6 critical dependencies** that must be provisioned in order before crawling
can begin:

1. **Environment Configuration** (`/etc/justnews/global.env` or repo `global.env`)

1. **MariaDB Database** (core persistence + orchestration state)

1. **ChromaDB** (vector embeddings for articles)

1. **vLLM Inference Server** (Mistral-7B on port 7060, already running ✅)

1. **MCP Bus** (inter-agent communication backbone)

1. **Crawler & Scheduler Agents** (crawling orchestration)

**Current Status**:

- ✅ vLLM Mistral-7B running on port 7060 (Mistral-7B-Instruct-v0.3, FP16 KV cache, 300W power limit)

- ❌ Global environment (`global.env`) missing

- ❌ MariaDB not initialized or checked

- ❌ ChromaDB not initialized or checked

- ❌ No agent services running

- ❌ No crawler process running

---

## Phase 1: Environment & Infrastructure Setup (Pre-Data)

### Task 1.1: Create Global Environment File

**Dependency**: None **Estimated Time**: 5 minutes **Evidence**:

- `infrastructure/systemd/QUICK_REFERENCE.md` lines 95–110 show minimal required env vars

- `scripts/init_database.py` line 211 checks for `MARIADB_*` env vars

- `config/system_config.json` contains defaults but needs runtime override

**Actions**:

```bash

## Create /etc/justnews/global.env (or repo-level global.env for dev)

## Required variables:

JUSTNEWS_PYTHON=/home/adra/miniconda3/envs/${CANONICAL_ENV:-justnews-py312}/bin/python
SERVICE_DIR=/home/adra/JustNews
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_DB=justnews
MARIADB_USER=justnews_user
MARIADB_PASSWORD=<set-secure-password>
CHROMA_HOST=localhost
CHROMA_PORT=8000
ARTICLE_EXTRACTOR_PRIMARY=trafilatura
ARTICLE_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CLUSTER_SIMILARITY_THRESHOLD=0.85
CANONICAL_ENV=justnews-py312

```

**Verification**:

```bash
source global.env && echo "✅ Environment loaded: MARIADB_HOST=$MARIADB_HOST"

```

---

### Task 1.2: Set Up MariaDB

**Dependency**: Task 1.1 (global.env) **Estimated Time**: 15 minutes **Evidence**:

- `infrastructure/systemd/setup_mariadb.sh` automates MariaDB install on systemd

- `scripts/init_database.py` expects MariaDB connection via `MARIADB_*` vars

- `database/utils/database_utils.py:get_db_config()` reads these env vars

**Actions**:

```bash

## Option A: Docker Compose (lightweight, for dev)

docker-compose -f scripts/dev/docker-compose.e2e.yml up -d mariadb

## Option B: Native systemd (production-like)

sudo ./infrastructure/systemd/setup_mariadb.sh \
  --user justnews_user \
  --password <secure-password>

## Option C: Manual if MariaDB already running

## Verify:

mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -h $MARIADB_HOST -e "SELECT 1;" \
  && echo "✅ MariaDB connection OK"

```

**Verification**:

```bash
./scripts/run_with_env.sh python -c \
  "from database.utils.database_utils import get_db_config; print(get_db_config())"

```

---

### Task 1.3: Set Up ChromaDB

**Dependency**: Task 1.1 (global.env) **Estimated Time**: 10 minutes **Evidence**:

- `scripts/chroma_diagnose.py` validates ChromaDB connectivity and auto-creates collections

- `database/utils/chromadb_utils.py` handles HTTP client + tenants

- ChromaDB port defaults to 8000 (from `config/system_config.json` and chroma_diagnose.py)

**Actions**:

```bash

## Option A: Docker (recommended for isolated vector DB)

docker run -d \
  --name chromadb \
  -p 8000:8000 \
  chromadb/chroma:latest

## Option B: systemd service (if available)

## (Check infrastructure/systemd for chroma unit files)

## Auto-create 'articles' collection:

cd /home/adra/JustNews && python scripts/chroma_diagnose.py --autocreate

```

**Verification**:

```bash
curl -s http://localhost:8000/api/v1/heartbeat | grep -q '{}' && echo "✅ ChromaDB responding"

```

---

## Phase 2: Database Schema Initialization (Data Layer)

### Task 2.1: Initialize Database Schema

**Dependency**: Task 1.2 (MariaDB running) **Estimated Time**: 5 minutes **Evidence**:

- `scripts/init_database.py` is the primary initialization entrypoint

- Lines 242–300 show creation of auth tables, knowledge graph tables, crawler jobs table, and admin user

- `tests/integration/test_persistence_schema.py` validates that articles, entities, training_examples, model_metrics tables exist

**Actions**:

```bash
cd /home/adra/JustNews
./scripts/run_with_env.sh python scripts/init_database.py

```

**Output should show**:

```

✅ Environment variables configured
✅ Database connection pool initialized
✅ Authentication tables created
✅ Knowledge graph tables created
✅ crawler jobs table created
👤 Creating initial admin user...
✅ Database initialization completed successfully!

Next steps:

1. Start the API server: python -m agents.archive.archive_api

1. Test authentication: POST /auth/login with admin credentials

1. Access API docs: http://localhost:8021/docs

```

**Verification**:

```bash
mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -D $MARIADB_DB \
  -e "SHOW TABLES;" | grep -E 'articles|entities|users' && echo "✅ Schema present"

```

---

### Task 2.2: Backup Existing Data (If Needed)

**Dependency**: Task 2.1 (schema exists) **Estimated Time**: 5–15 minutes (depending on data volume) **Evidence**:

- `backup_article_data.py` provides backup + restore utilities

- Saves MariaDB dumps + ChromaDB snapshots to `./database_backups/backup_<timestamp>/`

**Actions** (Optional, only if data already exists):

```bash
./scripts/run_with_env.sh python backup_article_data.py

```

---

## Phase 3: System Services Initialization (Agent Infrastructure)

### Task 3.1: Start MCP Bus

**Dependency**: Task 2.1 (database ready) **Estimated Time**: 5 minutes **Evidence**:

- `infrastructure/systemd/README.md` line 11 states: "Start GPU Orchestrator first"

- `agents/crawler_control/main.py` line 60–88 shows MCP registration pattern

- MCP Bus listens on port 8017 (from `config/system_config.json` line 8)

**Actions**:

```bash

## Option A: systemd (recommended for production)

sudo systemctl enable --now justnews@mcp_bus

## Option B: Direct Python (for dev/testing)

cd /home/adra/JustNews && ./scripts/run_with_env.sh python -m agents.mcp_bus.main

```

**Verification**:

```bash
curl -s http://localhost:8017/health && echo "✅ MCP Bus responding"

```

---

### Task 3.2: Start GPU Orchestrator

**Dependency**: Task 3.1 (MCP Bus running), vLLM already running on 7060 **Estimated Time**: 10 minutes (model loading
included) **Evidence**:

- `infrastructure/systemd/README.md` lines 8–10 emphasize "GPU Orchestrator first"

- GPU orchestrator gates model availability for all downstream agents (lines 11–19)

- Listens on port 8014

**Actions**:

```bash

## Option A: systemd (recommended)

sudo systemctl enable --now justnews@gpu_orchestrator
sleep 10
curl -fsS http://127.0.0.1:8014/ready

## Option B: Direct Python

cd /home/adra/JustNews && ./scripts/run_with_env.sh python -m agents.gpu_orchestrator.main

```

**Verification**:

```bash
curl -s http://localhost:8014/health | jq '.status' && echo "✅ GPU Orchestrator ready"
curl -s http://localhost:8014/models/status | jq '.models' | grep -i mistral

```

---

### Task 3.3: Start Core Agent Services (Critical Path)

**Dependency**: Task 3.2 (GPU Orchestrator READY) **Estimated Time**: 15 minutes **Evidence**:

- `infrastructure/systemd/scripts/enable_all.sh` starts all services with correct ordering

- `infrastructure/systemd/QUICK_REFERENCE.md` lines 40–60 define port map and health endpoints

- Crawler control on port 8016, Crawler agent on port 8015

**Critical services for crawling** (in order):

1. **Crawler** (port 8015) – primary crawling engine

1. **Crawler Control** (port 8016) – crawl orchestration + scheduling UI

1. **Analyst** (port 8004) – article analysis (optional but recommended)

1. **Memory** (port 8007) – semantic memory for article storage

**Actions**:

```bash

## Option A: systemd (recommended)

sudo ./infrastructure/systemd/scripts/enable_all.sh start

## Option B: Manual systemd per-service

for svc in crawler crawler_control analyst memory; do
  sudo systemctl enable --now justnews@$svc
done

## Option C: Direct Python (for dev)

cd /home/adra/JustNews
./scripts/run_with_env.sh python -m agents.crawler.main &
./scripts/run_with_env.sh python -m agents.crawler_control.main &

```

**Verification**:

```bash
./infrastructure/systemd/scripts/health_check.sh

## Or manual:

for port in 8015 8016 8004 8007; do
  curl -s http://localhost:$port/health && echo "✅ Port $port OK"
done

```

---

## Phase 4: Crawling & Data Ingestion (Database Filling)

### Task 4.1: Verify Crawl Profiles Exist

**Dependency**: Task 3.3 (crawler services running) **Estimated Time**: 5 minutes **Evidence**:

- `config/crawl_profiles/` contains YAML files for each domain

- `crawl_and_scrape_stack.md` section 5 describes profile-driven configuration

- `agents/crawler_control/crawl_profiles.py` loads and expands profiles at runtime

**Current profiles available**:

- `base.yaml` – default profile template

- `bbc.yaml` – BBC News profile

**Actions**:

```bash

## Check existing profiles

ls -la config/crawl_profiles/
cat config/crawl_profiles/base.yaml

## Validate profile expansion (dry-run)

./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py --dry-run

```

**Expected Output**: Dry-run should show crawl jobs that would execute (no articles fetched)

---

### Task 4.2: Run Minimal Live Crawl Test

**Dependency**: Task 4.1 (profiles exist) **Estimated Time**: 10–30 minutes (depending on site responsiveness)
**Evidence**:

- `live_crawl_test.py` provides end-to-end crawl test with BBC, Reuters, AP News, etc.

- Tests extraction, database persistence, and embedding generation

- Configurable article count and concurrency

**Actions**:

```bash

## Small test: 3 sites × 5 articles each = 15 articles

cd /home/adra/JustNews
./scripts/run_with_env.sh python live_crawl_test.py --sites 3 --articles 5

## Or larger test: 20 sites × 40 articles = 800 articles (recommended for training data)

./scripts/run_with_env.sh python live_crawl_test.py --sites 20 --articles 40

```

**Verification**:

```bash

## Query articles in database

mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -D $MARIADB_DB \
  -e "SELECT COUNT(*) AS article_count FROM articles;"

## Query ChromaDB collection

curl -s -X POST http://localhost:8000/api/v1/collections/articles/count \
  -H "Content-Type: application/json" \
  -d '{}' | jq '.count'

```

---

### Task 4.3: Run Scheduler-Based Hourly Crawls

**Dependency**: Task 4.2 (crawler working, articles stored) **Estimated Time**: 10 minutes setup + ongoing execution
**Evidence**:

- `config/crawl_schedule.yaml` defines hourly batches per domain

- `scripts/ops/run_crawl_schedule.py` is the orchestration entry-point (lines 1–80)

- Designed for systemd timer execution but supports ad-hoc runs

**Actions**:

```bash

## Ad-hoc dry-run to validate schedule

./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py \
  --schedule config/crawl_schedule.yaml \
  --dry-run

## Ad-hoc single execution

./scripts/run_with_env.sh python scripts/ops/run_crawl_schedule.py \
  --schedule config/crawl_schedule.yaml

## Setup systemd timer for hourly execution (production)

sudo cp infrastructure/systemd/units/justnews-crawl-scheduler.timer /etc/systemd/system/
sudo cp infrastructure/systemd/units/justnews-crawl-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now justnews-crawl-scheduler.timer

```

**Verification**:

```bash

## Check timer status

sudo systemctl status justnews-crawl-scheduler.timer

## Check recent crawl logs

tail -f /var/log/justnews/crawl_scheduler.log

## Query latest articles

mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -D $MARIADB_DB \
  -e "SELECT title, domain, created_at FROM articles ORDER BY created_at DESC LIMIT 10;"

```

---

## Phase 5: Training Data Preparation (Optional but Recommended)

### Task 5.1: Generate Training Clusters

**Dependency**: Task 4.3 (600+ articles in database) **Estimated Time**: 20 minutes **Evidence**:

- `agents/analyst/main.py` provides article clustering via semantic similarity

- Clusters are used for multi-article reasoning tasks

- Threshold: `CLUSTER_SIMILARITY_THRESHOLD=0.85` (from global.env)

**Actions**:

```bash

## Generate clusters from existing articles

./scripts/run_with_env.sh python -c \
  "from agents.analyst.main import cluster_articles; cluster_articles()"

```

---

### Task 5.2: Validate Data Quality

**Dependency**: Task 5.1 (clusters exist) **Estimated Time**: 10 minutes **Evidence**:

- `tests/integration/test_persistence_schema.py` validates schema and smoke-inserts

- `database/utils/database_utils.py` provides connectivity checks

**Actions**:

```bash

## Run database smoke tests

./scripts/run_with_env.sh pytest tests/integration/test_persistence_schema.py -v

## Run crawler extraction tests

./scripts/run_with_env.sh pytest tests/agents/crawler -v

```

---

## Execution Timeline

### **Quick Start (30–45 minutes for core functionality)**

```

1. Task 1.1: Create global.env                          (5 min)

1. Task 1.2: Set up MariaDB                             (15 min)

1. Task 1.3: Set up ChromaDB                            (10 min)

1. Task 2.1: Initialize database schema                 (5 min)

1. Task 3.1–3.3: Start MCP Bus + orchestrator + agents  (30 min)

1. Task 4.2: Run minimal crawl test                     (20 min)
TOTAL: ~85 minutes

```

### **Full Production Setup (2–3 hours)**

All tasks above +

- Task 4.3: Set up systemd timer for hourly crawls

- Task 5.1–5.2: Generate training data + validate

---

## Dependency Graph

```

global.env (1.1)
├── MariaDB setup (1.2)
│   └── Schema init (2.1)
│       └── MCP Bus (3.1)
│           └── GPU Orchestrator (3.2)
│               └── Crawler agents (3.3)
│                   └── Live crawl test (4.2)
│                       └── Scheduler (4.3)
│                           └── Training clusters (5.1)
├── ChromaDB setup (1.3)
│   └── Used by crawler for embeddings (4.2)
└── Backup (2.2) - optional, post-crawling

```

---

## Success Criteria

✅ **System is Running When**:

1. `/health` endpoints return 200 OK for:

   - MCP Bus (8017)

   - GPU Orchestrator (8014, plus /ready → 200)

   - Crawler (8015)

   - Crawler Control (8016)

1. `articles` table has >100 rows

1. ChromaDB `articles` collection has embeddings for all stored articles

1. `curl http://localhost:7060/health` → HTTP 200 (vLLM still running)

✅ **Data Ingestion Working When**:

1. Running `scripts/ops/run_crawl_schedule.py` fetches articles without errors

1. Articles appear in database within 5 minutes of crawler job completion

1. Embeddings are generated and stored in ChromaDB

1. No critical errors in service logs

---

## Troubleshooting Quick Reference

| Issue | Check | Fix | |-------|-------|-----| | `MARIADB_HOST` not found | `echo $MARIADB_HOST` | Source global.env
first | | Port 8015 (crawler) not responding | `curl http://localhost:8015/health` | Ensure GPU Orchestrator is READY
first | | ChromaDB collection missing | `curl http://localhost:8000/api/v1/collections` | Run `chroma_diagnose.py
--autocreate` | | Articles not stored | Check MariaDB connection + schema | Run `init_database.py` again | | vLLM on
7060 crashed | `curl http://localhost:7060/health` | Relaunch: `./scripts/launch_vllm_mistral_7b.sh` | | No embeddings
generated | Check ChromaDB health + article count | Ensure embeddings table exists |

---

## Maintenance & Monitoring

**Daily Operations**:

```bash

## Check all services are running

./infrastructure/systemd/scripts/health_check.sh

## View crawl scheduler metrics

tail -f /var/log/justnews/crawl_scheduler.log

## Monitor database size

du -sh /var/lib/mysql/justnews || du -sh ~/justnews_data/

```

**Weekly Tasks**:

- Review crawl profiles for regressions (`config/crawl_profiles/`)

- Backup database: `backup_article_data.py`

- Check embedding coverage: `SELECT COUNT(*) FROM articles WHERE embedding IS NULL;`

---

## Notes & Caveats

1. **vLLM**: Already running on port 7060 (Mistral-7B-Instruct-v0.3). No changes needed unless model replacement is required.

1. **GPU Power Limit**: 300W cap applied to RTX 3090. Adjust if thermal issues occur.

1. **Conda Environment**: All scripts expect `justnews-py312`. Set `CANONICAL_ENV` if using different environment.

1. **Database Credentials**: Use strong passwords in production. Update `global.env` accordingly.

1. **ChromaDB**: Defaults to 8000. Ensure no port conflicts with other services.

---

## Next Steps After System is Running

Once data ingestion is working:

1. **Train LoRA adapters** per-agent using `scripts/train_qlora.py`

1. **Enable per-agent routing** in MCP Bus for inference requests

1. **Deploy fact-checking pipeline** using Reasoner + Critic agents

1. **Run synthesizer** for multi-document summaries

1. **Activate transparency audit** for evidence logging

---

**Last Updated**: December 18, 2025 **Maintainer**: Platform Ops Team
