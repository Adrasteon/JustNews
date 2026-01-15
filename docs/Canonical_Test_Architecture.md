# JustNews Canonical Test Architecture

## Overview

This document defines the canonical testing architecture for the JustNews platform. It explains how the system initializes test environments, manages resources (GPU/RAM), and structures the different tiers of testing (Unit vs. Mocked E2E vs. Real Infrastructure E2E).

## 1. Initialization Sequence

The testing environment is designed to be **hermetic** but **configurable**. Tests do not run against the production environment variables directly but use a layered loading strategy.

### The Loading Layer (`scripts/run_with_env.sh`)
This script is the entry point for all test execution. It performs the following initialization:

1.  **Global Defaults**: Sources `/etc/justnews/global.env` (or repository fallback).
2.  **Secret Overlay**: Loads credentials from `secrets.env` (if available).
3.  **Command Execution**: Runs the requested command (e.g., `pytest`) with these variables injected.

### The Python Hook (`tests/conftest.py`)
When `pytest` starts, `conftest.py`:
1.  **Path Injection**: Inserts the repository root into `sys.path` so `agents.*` and `common.*` imports work.
2.  **Environment Isolation**: Checks for `JUSTNEWS_GLOBAL_ENV`. If missing, it generates a temporary, minimal `global.env` to prevent tests from accidentally connecting to production services.
3.  **Metric Isolation**: Swaps the global Prometheus registry with a temporary test registry via the `isolate_stage_b_metrics` fixture.

## 2. Test Execution Wrappers

While you can run `pytest` directly, the **canonical** way to run tests is via the provided shell wrappers. These wrappers handle resource limits that prevent system crashes.

### Primary Runner: `scripts/run_live_tests.sh`
This is the standard interface for developers.

*   **Concurrency Control**: Defaults to `-n 6` workers using `pytest-xdist`. This specific number is tuned to prevent RAM exhaustion (OOM) caused by loading heavy embedding models in parallel.
*   **Environment Flags**: Automatically sets `TEST_GPU_AVAILABLE` based on flags.
*   **Preflight Checks**: fast-paths dependency checks to speed up repeated runs.

**Usage:**
```bash
./scripts/run_live_tests.sh [OPTIONS]
```

### Makefile Shortcuts
*   `make test`: Runs standard unit tests (excludes heavy integration/performance tests).
*   `make test-integration`: Runs only tests marked `@integration`.
*   `make pytest-local`: Invokes the safe shell wrapper.

## 3. Configuration (`pytest.ini`)

The `pytest.ini` file acts as the "Engine Room", defining the default behavior for *any* pytest invocation.

| Setting | Value | Purpose |
| :--- | :--- | :--- |
| `addopts` | `-n 6 --dist worksteal` | Enforces parallel execution with load balancing by default. |
| `log_cli` | `true` | Enables real-time logging output in the terminal (crucial for "Live" monitoring). |
| `pythonpath` | `. agents` | Ensures source discovery works for IDEs and CLI alike. |
| `markers` | `gpu`, `slow`, `integration` | Defines custom markers to categorize tests. |

## 4. Test Tiers

The suite is divided into three tiers. Understanding these distinctions resolves confusion about "E2E" tests.

### Tier 1: Unit & Mocked E2E (Run by Default)
*   **Scope**: Tests logic, agent workflows, and internal interactions.
*   **Behavior**: Mocks external calls (Twitter API, Web Scraping) but exercises the full internal pipeline.
*   **Example**: `tests/agents/synthesizer/test_synthesizer_publish_e2e.py`
    *   *Action*: "Publishes" an article.
    *   *Verification*: Checks that the internal "Publish" event was fired and metrics were recorded.
    *   *Infrastructure*: Uses in-memory or mocked DBs.

### Tier 2: Real Infrastructure E2E (Skipped by Default)
*   **Scope**: Validates integration with **real** external services running on localhost.
*   **Behavior**: connect to actual Redis (port 16379), MariaDB (port 13306), or vLLM.
*   **Trigger**: Requires environment variable `RUN_REAL_E2E=1`.
*   **Example**: `tests/e2e/test_orchestrator_real_e2e.py`
    *   *Action*: Submits a real job to a real Redis stream.
    *   *Skipped Reason*: `requires_real_e2e` marker finds `RUN_REAL_E2E != 1`.

### Tier 3: Performance & Safety
*   **Scope**: GPU load tests, memory leak checks.
*   **Trigger**: Requires `TEST_GPU_AVAILABLE=true`.
*   **Example**: `tests/test_gpu.py`

## 5. Flags and Options Reference

### `scripts/run_live_tests.sh` Options

| Flag | Description |
| :--- | :--- |
| `-n N`, `--workers N` | Set number of parallel workers (Default: 6). Use `0` for sequential debugging. |
| `--gpu` | Enable GPU tests. Sets `TEST_GPU_AVAILABLE=true`. |
| `--fast` | Skip tests marked as `@slow`. |
| `--sequential` | Alias for `-n 0`. Useful for debugging race conditions. |
| `--integration` | Run only tests marked `@integration`. |
| `--chroma` | Run only ChromaDB-related tests. |
| `-k "keyword"` | Run tests matching the keyword expression. |

### Key Environment Variables

| Variable | Default | Effect |
| :--- | :--- | :--- |
| `TEST_GPU_AVAILABLE` | `false` | If `true`, runs tests marked `@gpu`. |
| `RUN_REAL_E2E` | `0` | If `1`, runs tests requiring live Redis/DB services (`tests/e2e/`). |
| `ENABLE_CHROMADB_LIVE_TESTS`| `0` | If `1`, runs tests requiring a live ChromaDB setup. |
| `JUSTNEWS_GLOBAL_ENV` | *(Auto)* | Path to the config file to load. |

## 6. Metrics & Telemetry

The test suite validates the observability pipeline itself.

1.  **Isolation**: `conftest.py` creates a clean `CollectorRegistry` for each test context.
2.  **Recording**: Tests use `common.stage_b_metrics` to record events (e.g., `extraction_total.inc()`).
3.  **Visualization**: With `log_cli = true`, these metrics are printed to stdout during the test run, allowing "Live" verification of system activity.

## 7. Troubleshooting Common Issues

*   **VS Code / System Freeze**:
    *   *Cause*: Running `pytest` without arguments tries to spawn unlimited workers or loads too many heavy models (BERT/RoBERTa) into RAM simultaneously.
    *   *Solution*: Always use `./scripts/run_live_tests.sh` which enforces the `-n 6` limit.
*   **"Redis client not available" Skips**:
    *   *Cause*: Tier 2 (Real E2E) tests are trying to run but no Docker containers are active.
    *   *Solution*: Ignorable for standard dev loops. To run them, ensure `RUN_REAL_E2E=1` and services are up.
*   **"StatusCode.UNAVAILABLE" at end of run**:
    *   *Cause*: OpenTelemetry exporter trying to flush metrics after the test process has technically finished/closed the loop.
    *   *Solution*: Benign. Can be ignored if tests passed.
