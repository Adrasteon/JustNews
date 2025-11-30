#!/usr/bin/env bash
# Backwards-compatible wrapper for local pytest runs that prefer the canonical conda env
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Respect global CANONICAL_ENV if exported in environment (fallback is inside
# run_pytest_conda.sh). This wrapper simply delegates to run_pytest_conda.sh
# to ensure a single behavior for local & CI test runs.
exec "${SCRIPT_DIR}/run_pytest_conda.sh" "$@"
