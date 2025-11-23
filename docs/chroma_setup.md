---
title: ChromaDB Canonical Configuration and Bootstrap
---

# ChromaDB Canonical Configuration and Bootstrap

This document describes how to ensure that your environment is configured to use a single canonical ChromaDB instance and how to bootstrap a collection and tenant for the `JustNews` system.

## Goals
- Ensure a single canonical ChromaDB instance is used by all agents.
- Enforce fatal errors when a canonical Chroma is configured but not reachable or incorrect.
- Provide tools and scripts for operators to bootstrap and diagnose Chroma.

## Environment Variables
Set the following variables (recommended in `/etc/justnews/global.env`):

- `CHROMADB_HOST` — runtime Chroma host your agents will use (e.g., `localhost`)
- `CHROMADB_PORT` — runtime Chroma port your agents will use (e.g., `3307`)
- `CHROMADB_COLLECTION` — collection name to use (e.g., `articles`)

(_Optional_) Strict canonical enforcement:
- `CHROMADB_REQUIRE_CANONICAL` — if `1`, the agent will fail at startup if `CHROMADB_HOST/PORT` does not match canonical values.
- `CHROMADB_CANONICAL_HOST` & `CHROMADB_CANONICAL_PORT` — canonical host & port for this deployment. If canonical enforcement is enabled and the runtime host/port doesn't match, the service will abort start and provide diagnostic error messages.

## Operator Commands

Run the following to check and bootstrap your Chroma instance:

```bash
# Show configured DB / Chroma values
PYTHONPATH=. conda run -n justnews-py312 python scripts/print_db_config.py

# Diagnose Chroma endpoints and canonical settings
PYTHONPATH=. CHROMADB_REQUIRE_CANONICAL=1 CHROMADB_CANONICAL_HOST=localhost CHROMADB_CANONICAL_PORT=3307 \
  conda run -n justnews-py312 python scripts/chroma_diagnose.py --host localhost --port 3307 --autocreate

# If diagnosis shows missing tenant or collection, attempt to create them
PYTHONPATH=. conda run -n justnews-py312 python scripts/chroma_bootstrap.py --host localhost --port 3307 --tenant default_tenant --collection articles
```

## Troubleshooting
- If the diagnostic shows the root `MCP Bus Agent` text, double-check your CHROMADB_HOST/PORT environment values and adjust to your actual Chroma server (not the MCP Bus which runs on a hub port).
- If the bootstrap script fails due to permissions or API version, contact your Chroma host operator to create the tenant/collection.

## Production Note
For production, set `CHROMADB_REQUIRE_CANONICAL=1` and configure `CHROMADB_CANONICAL_HOST` and `CHROMADB_CANONICAL_PORT` in `/etc/justnews/global.env`. System startup scripts and agents will validate these settings and will abort with actionable logs if something is misconfigured.
