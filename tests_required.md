# Tests Required — prioritized list to improve coverage

This document summarizes the top source files with little or no test coverage (sorted by uncovered lines). Each entry
explains why it matters and gives suggested tests / next actions to increase coverage quickly.

> Note: These results were extracted from `coverage.xml` (current line coverage ~42.3%). The list prioritizes absolute uncovered lines and then low coverage rates.

---

## Top priority files (highest uncovered lines)

1. agents/common/auth_api.py — 637 total lines, 490 uncovered, line-rate 0.2308

  - Why: Auth API routes & helpers are mostly untested.

  - Tests to add: unit tests for request parsing/validation, error paths, and endpoints. Mock external services (token stores, DB).

1. agents/fact_checker/fact_checker_engine.py — 389 total, 345 uncovered, line-rate 0.1131

  - Why: Core engine logic has many untested branches.

  - Tests to add: unit tests for rule evaluation, edge cases, and integration tests with sample inputs.

1. agents/common/gpu_manager_production.py — 426 total, 324 uncovered, line-rate 0.2394

  - Why: Production GPU orchestration code paths untested.

  - Tests to add: unit tests for pool lifecycle, leader election, DB resilience (mock DB + GPU responses).

1. agents/common/embedding.py — 454 total, 319 uncovered, line-rate 0.2974

  - Why: Embedding/model-loading and error handling paths not covered.

  - Tests to add: unit tests around model loading, embeddings pipeline, and fallback/error flows (mock models).

1. monitoring/core/metrics_collector.py — 305 total, 305 uncovered, line-rate 0.0

  - Why: Zero coverage; critical to observability.

  - Tests to add: unit tests for metric parsing, aggregation, formatting, and mocking backend integration.

1. monitoring/core/performance_monitor.py — 305 total, 305 uncovered, line-rate 0.0

  - Tests to add: thresholds, trigger behaviors, and scheduled checks. Use small unit tests and a lightweight integration harness.

1. config/legacy/__init__.py — 349 total, 292 uncovered, line-rate 0.1633

  - Tests to add: config parsing, migration helpers, and backward compatibility scenarios.

1. monitoring/core/log_storage.py — 287 total, 287 uncovered, line-rate 0.0

  - Tests to add: storage write/read flows (mock store), pruning, retention policies.

1. monitoring/core/trace_storage.py — 283 total, 283 uncovered, line-rate 0.0

  - Tests to add: trace ingestion, lookup/index behaviours.

1. monitoring/core/trace_analyzer.py — 274 total, 274 uncovered, line-rate 0.0

    - Tests to add: trace analysis logic, heuristics, and outputs.

1. security/compliance/service.py — 274 total, 274 uncovered, line-rate 0.0

    - Tests to add: compliance rule checks, policy decision unit tests.

1. security/encryption/service.py — 266 total, 266 uncovered, line-rate 0.0

    - Tests to add: encryption/decryption paths, key handling with test keys.

1. security/monitoring/service.py — 266 total, 266 uncovered, line-rate 0.0

    - Tests to add: alerting and policy-monitoring tests.

1. monitoring/core/log_analyzer.py — 260 total, 260 uncovered, line-rate 0.0

    - Tests to add: log pattern detection, statistical checks.

1. training_system/core/training_coordinator.py — 368 total, 258 uncovered, line-rate 0.2989

    - Tests to add: training task lifecycle, DB interactions (mock DB), error/retry flows.

1. config/test_config_system.py — 256 total, 256 uncovered, line-rate 0.0

    - Tests to add: unit tests for config helpers, schema checks.

1. agents/sites/generic_site_crawler.py — 353 total, 254 uncovered, line-rate 0.2805

    - Tests to add: parsing edge-cases, fallback scraping flows and error handling.

1. config/validation/__init__.py — 290 total, 244 uncovered, line-rate 0.1586

    - Tests to add: validation chains and error messages.

1. agents/hitl_service/app.py — 563 total, 244 uncovered, line-rate 0.5666

    - Tests to add: API endpoint tests for HITL ingest/QA/training paths.

1. monitoring/core/trace_processor.py — 242 total, 242 uncovered, line-rate 0.0

    - Tests to add: trace processing unit tests, correctness of transforms.

(See coverage.xml for a longer list — several monitoring/* and security/* files are completely untested.)

---

## Quick roadmap — actionable next steps

1. Fast wins (1–2 days each)

  - Add unit tests for `agents/common/auth_api.py` (routes & validation). This yields high coverage delta because file is large and mostly untested.

  - Add tests for `agents/common/embedding.py` focusing on model loading and error handling.

1. High impact (2–4 days each)

  - Add unit+integration tests for `agents/fact_checker/fact_checker_engine.py` and `training_system/core/training_coordinator.py` to cover core logic and DB interaction paths (mock DB).

  - Add tests for `agents/sites/generic_site_crawler.py` parsing, using small HTML fixtures.

1. Monitoring + security coverage push (longer effort, 1–2 weeks)

  - Monitoring files under `monitoring/core/` are mostly untested — create a test harness mocking backends and produce coverage across `metrics_collector`, `log_*`, `trace_*` modules.

  - Security service modules (authentication, encryption, compliance) need unit tests for safe handling of secrets and policy logic; use test-only keys and mocks.

1. Coverage tooling

  - Run coverage with branch coverage enabled: `coverage run --branch -m pytest` and analyze misses.

  - Add small targeted tests to exercise conditionals and exception branches.

---

## How I generated this list

- Parsed `coverage.xml` and sorted files by the number of uncovered lines, then used that as the primary priority metric. Secondary priority factor is line-rate (lower -> higher priority).

---

If you want, I can:

- scaffold unit tests for the top 3 files and run them, or

- create a small task board (tickets) with estimates per file so you can assign work incrementally.

Which option would you like me to take next?
