#!/usr/bin/env bash
# Run pytest using the canonical project conda environment when available
set -euo pipefail

CANONICAL_ENV="${CANONICAL_ENV:-justnews-py312}"

if command -v conda >/dev/null 2>&1; then
    # If the environment exists, run tests inside it
    if conda env list 2>/dev/null | awk '{print $1}' | grep -xq "$CANONICAL_ENV"; then
        echo "Running pytest inside conda env: $CANONICAL_ENV"
        conda run -n "$CANONICAL_ENV" pytest "$@"
        exit $?
    fi
fi

if command -v pytest >/dev/null 2>&1; then
    echo "Conda env $CANONICAL_ENV not found — falling back to system pytest"
    pytest "$@"
    exit $?
fi

echo "ERROR: pytest not found and conda env '${CANONICAL_ENV}' is not available."
echo "Please create the conda environment from environment.yml or install pytest locally."
exit 2
