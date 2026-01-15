#!/bin/bash
# JustNews Live Test Runner with Resource Management
# 
# This script runs the full test suite with controlled parallelism to prevent
# the RAM exhaustion issue that previously crashed VS Code due to 2000+ process spawns.
#
# System Resources:
# - RAM: 31GB
# - Swap: 32GB (upgraded from 8GB)
# - Total: 63GB
#
# Resource Strategy:
# - Controlled parallelism: 6 workers (pytest-xdist)
# - Session-scoped fixtures for embedding models & database clients
# - Process limit: 1000 max (prevents runaway spawning)
# - Worker distribution: worksteal (better load balancing)

set -e

# --- Live Test Configuration ---
# Force enabling of live integrations matching the "Live Test Runner" purpose
export ENABLE_CHROMADB_LIVE_TESTS=1
export ENABLE_DB_INTEGRATION_TESTS=1
export TEST_GPU_AVAILABLE=true
export JUSTNEWS_GLOBAL_ENV=${JUSTNEWS_GLOBAL_ENV:-/etc/justnews/global.env}
export CHROMADB_REQUIRE_CANONICAL=0

# Optimization: Skip repetitive preflight checks during heavy test runs
export SKIP_PREFLIGHT_CHECK=1

# Resource limits to prevent thrashing under parallel load
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false
# -------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== JustNews Live Test Suite ===${NC}"
echo ""

# Check if pytest-xdist is installed
if ! python -c "import xdist" 2>/dev/null; then
    echo -e "${YELLOW}Warning: pytest-xdist not installed. Installing...${NC}"
    pip install pytest-xdist
fi

# Show current resource status
echo -e "${GREEN}Current System Resources:${NC}"
free -h
echo ""
swapon --show
echo ""

# Parse command line arguments
WORKERS="${PYTEST_WORKERS:-6}"
MARKERS=""
VERBOSE=""
COVERAGE=""
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--workers)
            WORKERS="$2"
            shift 2
            ;;
        -m|--markers)
            MARKERS="-m $2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE="-vv"
            shift
            ;;
        -k|--keyword)
            KEYWORD="-k $2"
            shift 2
            ;;
        --cov)
            COVERAGE="--cov=agents --cov=database --cov-report=html --cov-report=term"
            shift
            ;;
        --gpu)
            MARKERS="-m gpu"
            shift
            ;;
        --integration)
            MARKERS="-m integration"
            shift
            ;;
        --chroma)
            MARKERS="-m chroma"
            shift
            ;;
        --fast)
            # Fast mode: skip slow tests
            MARKERS="-m 'not slow'"
            shift
            ;;
        --sequential)
            # For debugging: run sequentially
            WORKERS="0"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -n, --workers N       Number of parallel workers (default: 6)"
            echo "  -m, --markers EXPR    Run tests matching markers (e.g., 'gpu', 'integration')"
            echo "  -k, --keyword EXPR    Run tests matching keyword expression"
            echo "  -v, --verbose         Verbose output"
            echo "  --cov                 Enable coverage reporting"
            echo "  --gpu                 Run GPU tests only"
            echo "  --integration         Run integration tests only"
            echo "  --chroma              Run ChromaDB tests only"
            echo "  --fast                Skip slow tests"
            echo "  --sequential          Run tests sequentially (for debugging)"
            echo "  -h, --help            Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                           # Run all tests with 6 workers"
            echo "  $0 -n 4                      # Run with 4 workers"
            echo "  $0 --gpu --cov               # Run GPU tests with coverage"
            echo "  $0 -k 'test_database'        # Run tests matching keyword"
            echo "  $0 --sequential -vv          # Debug mode: sequential + verbose"
            exit 0
            ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"
            shift
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="pytest"

if [ "$WORKERS" != "0" ]; then
    PYTEST_CMD="$PYTEST_CMD -n $WORKERS --dist worksteal"
    echo -e "${GREEN}Running with $WORKERS parallel workers${NC}"
else
    echo -e "${YELLOW}Running sequentially (debugging mode)${NC}"
fi

if [ -n "$MARKERS" ]; then
    PYTEST_CMD="$PYTEST_CMD $MARKERS"
    echo -e "${GREEN}Filtering by markers: $MARKERS${NC}"
fi

if [ -n "$KEYWORD" ]; then
    PYTEST_CMD="$PYTEST_CMD $KEYWORD"
    echo -e "${GREEN}Filtering by keyword: $KEYWORD${NC}"
fi

if [ -n "$VERBOSE" ]; then
    PYTEST_CMD="$PYTEST_CMD $VERBOSE"
fi

if [ -n "$EXTRA_ARGS" ]; then
    PYTEST_CMD="$PYTEST_CMD $EXTRA_ARGS"
    echo -e "${GREEN}Passing extra arguments: $EXTRA_ARGS${NC}"
fi

if [ -n "$COVERAGE" ]; then
    PYTEST_CMD="$PYTEST_CMD $COVERAGE"
    echo -e "${GREEN}Coverage reporting enabled${NC}"
fi

echo ""
echo -e "${GREEN}Executing: $PYTEST_CMD${NC}"
echo ""

# Set resource limits
export PYTEST_MAX_WORKERS="$WORKERS"

# Run tests
echo "Loading secrets/config via run_with_env.sh..."
"$SCRIPT_DIR/run_with_env.sh" $PYTEST_CMD

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
else
    echo -e "${RED}✗ Some tests failed (exit code: $EXIT_CODE)${NC}"
fi

# Show final resource usage
echo ""
echo -e "${GREEN}Final Resource Status:${NC}"
free -h

exit $EXIT_CODE
