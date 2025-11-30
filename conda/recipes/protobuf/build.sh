#!/usr/bin/env bash
set -euo pipefail

# Build step for protobuf python extension inside conda-build environment
echo "Building protobuf ${PKG_VERSION:-(unknown)} inside conda-build..."

# Use pip to build wheel then install into the build prefix. Avoid upgrading
# pip/setuptools here — the build environment should provide a working pip
# so upgrading via PyPI is not required and may fail in locked CI networks.
python -m pip --version || true
python -m pip wheel . -w dist --no-deps
python -m pip install dist/*.whl --no-deps --prefix "$CONDA_PREFIX"

echo "Finished building protobuf package (check CONDA_PREFIX: $CONDA_PREFIX)"
