# JustNews System Startup Documentation Index

## Quick Navigation

**Start here**: [STARTUP_SUMMARY.md](./STARTUP_SUMMARY.md) — 2 minute overview of the plan

**Then choose your role**:
- 👨‍💻 **I want to execute commands**: Use [SYSTEM_STARTUP_CHECKLIST.md](./SYSTEM_STARTUP_CHECKLIST.md) ← copy-paste approach
- 📖 **I want to understand everything**: Use [ACTION_PLAN_GET_SYSTEM_RUNNING.md](./ACTION_PLAN_GET_SYSTEM_RUNNING.md) ← detailed guide

---

## Document Breakdown

| Document | Audience | Purpose | Length |
|----------|----------|---------|--------|
| [STARTUP_SUMMARY.md](./STARTUP_SUMMARY.md) | Everyone | Overview + key findings + why the plan works | 2 min read |
| [SYSTEM_STARTUP_CHECKLIST.md](./SYSTEM_STARTUP_CHECKLIST.md) | Operators | Copy-paste command blocks + checkboxes | 5 min to scan |
| [ACTION_PLAN_GET_SYSTEM_RUNNING.md](./ACTION_PLAN_GET_SYSTEM_RUNNING.md) | Engineers | Full context + evidence + troubleshooting | 15 min to read |

---

## The Plan in 30 Seconds

1. **Create `global.env`** with MariaDB + ChromaDB connection details (5 min)
2. **Start MariaDB + ChromaDB** (Docker or native) (20 min)
3. **Initialize database schema**: `python scripts/init_database.py` (5 min)
4. **Start MCP Bus** → **GPU Orchestrator** → **Crawler agents** (30 min)
5. **Run crawl test**: `python live_crawl_test.py --sites 3 --articles 5` (20 min)
6. **Verify**: Articles in MariaDB + embeddings in ChromaDB

**Total**: ~90 minutes for full production-ready system

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     JustNews System                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │  Input: News Sites (BBC, Reuters, AP, etc)    │    │
│  └────────────┬─────────────────────────────────┘    │
│               │                                        │
│               ▼                                        │
│  ┌────────────────────────────────────────────────┐    │
│  │  Crawler Engine (port 8015)                   │    │
│  │  └─ Fetch HTML, JavaScript rendering         │    │
│  │  └─ Paywall detection, modal handling         │    │
│  │  └─ User-agent rotation, stealth headers      │    │
│  └────────┬───────────────────────────────────────┘    │
│           │                                             │
│           ▼                                             │
│  ┌────────────────────────────────────────────────┐    │
│  │  Extraction Pipeline                          │    │
│  │  └─ Trafilatura (primary)                      │    │
│  │  └─ Readability, jusText (fallbacks)           │    │
│  └────────┬───────────────────────────────────────┘    │
│           │                                             │
│      ┌────┴──────────────────┐                          │
│      ▼                        ▼                         │
│  ┌─────────────┐         ┌──────────────┐              │
│  │ MariaDB     │         │ ChromaDB     │              │
│  │ (Articles)  │         │ (Embeddings) │              │
│  │ (Entities)  │         │ (Vectors)    │              │
│  │ (Metadata)  │         └──────────────┘              │
│  └─────────────┘                                       │
│                                                        │
│  ┌──────────────────────────────────────────────┐      │
│  │  Orchestration Layer                        │      │
│  │  ├─ MCP Bus (8017) - inter-agent comms       │      │
│  │  ├─ GPU Orchestrator (8014) - gates models   │      │
│  │  ├─ Crawler Control (8016) - scheduling UI   │      │
│  │  └─ Optional: Analyst, Memory agents         │      │
│  └──────────────────────────────────────────────┘      │
│                                                        │
│  ┌──────────────────────────────────────────────┐      │
│  │  External Services (Already Running)         │      │
│  │  └─ vLLM Mistral-7B (port 7060)              │      │
│  └──────────────────────────────────────────────┘      │
│                                                        │
└─────────────────────────────────────────────────────────┘
```

---

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| vLLM Mistral-7B | ✅ Running | Port 7060, FP16 KV cache, 300W GPU cap |
| MariaDB | ❌ Not checked | Need to verify or start |
| ChromaDB | ❌ Not checked | Need to verify or start |
| MCP Bus | ❌ Not started | Port 8017 |
| GPU Orchestrator | ❌ Not started | Port 8014, gates models |
| Crawler Agent | ❌ Not started | Port 8015 |
| Crawler Control | ❌ Not started | Port 8016, scheduling UI |
| Database Schema | ❌ Not initialized | Tables not created yet |
| Data | ❌ Empty | No articles ingested |

---

## Key Constraints to Remember

1. **GPU Orchestrator must reach `/ready` before crawlers start**
   - Crawlers check this and fail silently if not ready
   - The plan explicitly waits for this in Phase 3.2

2. **Database schema must exist before crawlers can insert articles**
   - Run `init_database.py` in Phase 2
   - This is checked by crawler at runtime

3. **ChromaDB collection must exist or embeddings fail silently**
   - Run `chroma_diagnose.py --autocreate` in Phase 1.3
   - Crawler won't retry if this fails

4. **All env vars in `global.env` are read at service startup**
   - Changes require service restart
   - Good to validate early (Phase 1.1)

---

## Success Metrics

✅ **System Running**:
- All `/health` endpoints return 200 OK
- `/ready` endpoint on orchestrator returns 200 OK
- All systemd units show `active (running)`

✅ **Data Flowing**:
- MariaDB `articles` table has rows
- ChromaDB `articles` collection has embeddings
- No ERROR-level logs in past 5 minutes
- Crawler completes jobs in <60 seconds per site

---

## Troubleshooting Cheat Sheet

```bash
# Check all services
./infrastructure/systemd/scripts/health_check.sh

# View logs for a specific agent
journalctl -u justnews@crawler -f

# Check database connectivity
mysql -u $MARIADB_USER -p$MARIADB_PASSWORD -h $MARIADB_HOST -e "SELECT COUNT(*) FROM articles;"

# Check ChromaDB
curl -s http://localhost:8000/api/v1/heartbeat

# Restart a specific service
sudo systemctl restart justnews@crawler

# Stop all services (coordinated)
sudo ./infrastructure/systemd/canonical_system_startup.sh stop
```

---

## Files You'll Need

```
Required (create during Phase 1):
├── /etc/justnews/global.env (or ./global.env in repo)
│   └── Database URLs, paths, thresholds

Provided in repo (already there):
├── scripts/init_database.py ..................... Phase 2
├── scripts/ops/run_crawl_schedule.py ........... Phase 4.3
├── live_crawl_test.py .......................... Phase 4.2
├── config/crawl_profiles/*.yaml ............... Phase 4.1
├── config/crawl_schedule.yaml ................. Phase 4.3
├── infrastructure/systemd/ .................... Phase 3 & monitoring
├── agents/crawler/ ............................ Phase 3.3
├── agents/gpu_orchestrator/ ................... Phase 3.2
└── agents/mcp_bus/ ............................ Phase 3.1
```

---

## Execution Paths

### Path A: Quick Test (30 min)
Just want to see if system works?
```
1. Create global.env (5 min)
2. Start MariaDB + ChromaDB (15 min)
3. Run init_database.py (5 min)
4. Start crawler services manually (15 min)
5. Run live_crawl_test.py with --sites 1 --articles 3
```
Result: 10-15 articles in database, proof of concept

### Path B: Full Production (90 min)
Setting up for real data ingestion?
```
Follow ACTION_PLAN.md phases 1–5 sequentially
```
Result: 500+ articles/hour via scheduler, full pipeline

### Path C: Just the Crawler (45 min)
Only want to test crawling without full orchestration?
```
1. Create global.env
2. Start MariaDB + ChromaDB
3. Run init_database.py
4. python -m agents.crawler.main (direct, no MCP)
5. POST http://localhost:8015/start_crawl with manual payload
```
Result: Direct crawler testing, no scheduling

---

## Important: You Already Have

✅ **vLLM Mistral-7B** on port 7060 is running and tested  
✅ **GPU setup** at 300W power cap (stable)  
✅ **All source code** already in place  
✅ **Conda environment** `justnews-py312` ready  
✅ **Configuration files** in `config/`  
✅ **Database initialization scripts** ready to run  

**You just need to:**
❌ Create `global.env`  
❌ Start MariaDB + ChromaDB  
❌ Initialize schema  
❌ Start agents  
❌ Start crawling  

**Total setup time: ~90 minutes**

---

## Questions? Refer to:

| Question | Document | Section |
|----------|----------|---------|
| "What's the big picture?" | STARTUP_SUMMARY.md | Findings |
| "What do I run first?" | SYSTEM_STARTUP_CHECKLIST.md | Phase 1.1 |
| "Why does GPU Orchestrator matter?" | ACTION_PLAN_GET_SYSTEM_RUNNING.md | Phase 3.2 |
| "How do I know if it's working?" | ACTION_PLAN_GET_SYSTEM_RUNNING.md | Success Criteria |
| "What if X fails?" | ACTION_PLAN_GET_SYSTEM_RUNNING.md | Troubleshooting |
| "How long will this take?" | SYSTEM_STARTUP_CHECKLIST.md | Time Estimate |

---

**Created**: December 18, 2025  
**Last Updated**: December 18, 2025  
**Status**: Ready for execution
