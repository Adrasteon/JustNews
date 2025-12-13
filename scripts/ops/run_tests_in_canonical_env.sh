#!/usr/bin/env bash
# run_tests_in_canonical_env.sh — Run pytest inside the canonical conda env `justnews-py312`
set -euo pipefail

CONDA_ENV_NAME="justnews-py312"
PYTEST_ARGS=("${@:-tests/system}")

run_with_conda() {
  if command -v conda >/dev/null 2>&1; then
    echo "Running tests via: conda run -n ${CONDA_ENV_NAME} pytest ${PYTEST_ARGS[*]}"
    conda run -n "${CONDA_ENV_NAME}" pytest "${PYTEST_ARGS[@]}"
    return 0
  fi
  if command -v mamba >/dev/null 2>&1; then
    echo "Running tests via: mamba run -n ${CONDA_ENV_NAME} pytest ${PYTEST_ARGS[*]}"
    mamba run -n "${CONDA_ENV_NAME}" pytest "${PYTEST_ARGS[@]}"
    return 0
  fi
  if command -v micromamba >/dev/null 2>&1; then
    echo "Running tests via: micromamba run -n ${CONDA_ENV_NAME} pytest ${PYTEST_ARGS[*]}"
    micromamba run -n "${CONDA_ENV_NAME}" pytest "${PYTEST_ARGS[@]}"
    return 0
  fi
  return 1
}

run_with_python_path() {
  # If CANONICAL_PYTHON is set and executable, prefer that.
  if [[ -n "${CANONICAL_PYTHON:-}" && -x "${CANONICAL_PYTHON}" ]]; then
    echo "Running tests via: ${CANONICAL_PYTHON} -m pytest ${PYTEST_ARGS[*]}"
    "${CANONICAL_PYTHON}" -m pytest "${PYTEST_ARGS[@]}"
    return 0
  fi
  
  # Try common conda/miniconda install locations for portable detection
  CANDIDATES=(
    "${HOME}/miniconda3/envs/${CONDA_ENV_NAME}/bin/python"
    "${HOME}/.miniconda3/envs/${CONDA_ENV_NAME}/bin/python"
    "/opt/conda/envs/${CONDA_ENV_NAME}/bin/python"
    "/usr/local/miniconda3/envs/${CONDA_ENV_NAME}/bin/python"
    "${HOME}/anaconda3/envs/${CONDA_ENV_NAME}/bin/python"
  )
  for candidate in "${CANDIDATES[@]}"; do
    if [[ -x "${candidate}" ]]; then
      CANONICAL_PYTHON="${candidate}"
      echo "Detected canonical python at: ${CANONICAL_PYTHON}"
      echo "Running tests via: ${CANONICAL_PYTHON} -m pytest ${PYTEST_ARGS[*]}"
      "${CANONICAL_PYTHON}" -m pytest "${PYTEST_ARGS[@]}"
      return 0
    fi
  done
  
  return 1
}

echo "Attempting to run pytest in canonical environment: ${CONDA_ENV_NAME}"
if run_with_conda; then
  exit 0
fi

if run_with_python_path; then
  exit 0
fi

echo "Could not locate conda/mamba/micromamba or CANONICAL_PYTHON; please ensure 'conda' is installed and the '${CONDA_ENV_NAME}' env exists or set CANONICAL_PYTHON to the env's python path." >&2
exit 2
