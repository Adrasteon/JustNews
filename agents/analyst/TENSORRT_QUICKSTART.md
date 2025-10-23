---
title: TensorRT Quickstart (safe, no-GPU stub)
description: Auto-generated description for TensorRT Quickstart (safe, no-GPU stub)
tags: [documentation]
status: current
last_updated: 2025-09-12
---

# TensorRT Quickstart (safe, no-GPU stub)

This file explains how to run a safe, developer-friendly stub for the TensorRT engine build process.

Purpose
- Provide a predictable local flow that documents what the native TensorRT compiler would do.
- Avoid requiring GPUs, TensorRT, or CUDA to run a quick "build check" during development.

Files
- `scripts/compile_tensorrt_stub.py` — safe stub that either calls the real compiler (if available) or creates marker engine files to emulate a successful build.
 - `tools/build_engine/build_engine.py` — host-native scaffold to run the native compiler when available or create marker engines.

Quick checks
1. Check-only (no changes):

   python scripts/compile_tensorrt_stub.py --check-only

   This verifies whether the real compiler and runtime are importable and reports what would be built.

2. Create marker engines (safe, no GPU required):

   python scripts/compile_tensorrt_stub.py --build-markers

   This creates small marker `.engine` files and matching metadata JSON in `agents/analyst/tensorrt_engines/` so runtime code paths that check for engine artifacts will see them.

Notes
- The stub is intentionally conservative: it will only call the real compiler if the required native packages are present. Otherwise it writes marker files and returns success.
- Use this when running CI jobs or developer checks that must not require GPUs.

Recommended next steps
- Add a CI job that runs `--check-only` to assert environment capability.
- Add unit tests that mock `tensorrt`/`torch` to validate the logic in `native_tensorrt_compiler.py` without hardware.

## See also

- Technical Architecture: markdown_docs/TECHNICAL_ARCHITECTURE.md
- Documentation Catalogue: docs/DOCUMENTATION_CATALOGUE.md

