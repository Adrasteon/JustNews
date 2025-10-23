---
title: Secrets handling (minimal guidance)
description: Auto-generated description for Secrets handling (minimal guidance)
tags: [documentation]
status: current
last_updated: 2025-10-18
---

# Secrets handling (minimal guidance)

This document describes a minimal, practical approach to managing secrets for a native JustNews deployment.

1. Use systemd EnvironmentFile for per-service env vars. Create `/etc/justnews/justnews.env` with strict permissions (600) and owned by root.
2. Avoid committing secrets to Git. Store only `*.example` templates in repo (e.g., `deploy/systemd/examples/justnews.env.example`).
3. For production use, integrate a secrets manager (HashiCorp Vault, AWS Secrets Manager). Mount short-lived token files or use the systemd `Environment=` option to read from a secure agent.
4. Ensure the `justnews` service account cannot read other users' secrets. Use file perms and systemd `ProtectSystem`/`ProtectHome` where appropriate.
5. Document where each env var is required (DB, MODEL_STORE_ROOT, API keys) and refer to `config/justnews.env.example`.
