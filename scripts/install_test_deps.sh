#!/bin/bash
# Install pytest-xdist for parallel testing
# Required for the new controlled parallelism test infrastructure

echo "Installing pytest-xdist for controlled parallel testing..."

if command -v conda &> /dev/null && [ -n "$CONDA_DEFAULT_ENV" ]; then
    echo "Using conda environment: $CONDA_DEFAULT_ENV"
    conda install -y -c conda-forge pytest-xdist
else
    echo "Using pip..."
    pip install pytest-xdist>=3.5.0
fi

echo ""
echo "✓ pytest-xdist installed successfully!"
echo ""
echo "You can now run tests with controlled parallelism:"
echo "  ./scripts/run_live_tests.sh"
echo ""
echo "Or directly with pytest:"
echo "  pytest -n 6  # 6 parallel workers"
