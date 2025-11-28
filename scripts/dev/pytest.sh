#!/usr/bin/env bash
# Wrapper to run pytest under the justnews-py312 conda environment.
# Usage: scripts/dev/pytest.sh [pytest args]

set -euo pipefail

ENV_NAME="justnews-py312"

# Prefer explicit PYTHONPATH so tests import from repo root
export PYTHONPATH="$(pwd)"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found in PATH. Please install Miniconda/Anaconda or run pytest via your preferred Python environment."
  exit 1
fi

echo "Running pytest in conda env: ${ENV_NAME}"
conda run -n "${ENV_NAME}" pytest "$@"
