#!/bin/bash
# justnews-start-agent.sh - Standardized agent startup script
# Provides consistent startup behavior across all JustNews agents

set -euo pipefail

# Configuration
SCRIPT_NAME="$(basename "$0")"
AGENT_NAME="${1:-}"

# Optionally prime env from global file early for root resolution
if [[ -r "/etc/justnews/global.env" ]]; then
    # shellcheck source=/dev/null
    source "/etc/justnews/global.env"
fi

# Resolve project root robustly (WorkingDirectory -> JUSTNEWS_ROOT -> SERVICE_DIR -> script-relative -> fallback)
resolve_project_root() {
    # Helper: consider a directory a valid repo root only if it contains expected agent folders
    _is_valid_root() {
        local root="$1"
        [[ -d "$root/agents" ]] && [[ -d "$root/agents/gpu_orchestrator" ]] && [[ -d "$root/infrastructure/systemd" ]]
    }

    local cwd; cwd="$(pwd)"
    if _is_valid_root "$cwd"; then
        echo "$cwd"; return 0
    fi

    if [[ -n "${JUSTNEWS_ROOT:-}" ]] && _is_valid_root "$JUSTNEWS_ROOT"; then
        echo "$JUSTNEWS_ROOT"; return 0
    fi

    if [[ -n "${SERVICE_DIR:-}" ]]; then
        if _is_valid_root "$SERVICE_DIR"; then
            echo "$SERVICE_DIR"; return 0
        fi
        if _is_valid_root "$SERVICE_DIR/JustNewsAgent"; then
            echo "$SERVICE_DIR/JustNewsAgent"; return 0
        fi
        if _is_valid_root "$SERVICE_DIR/JustNewsAgent-Clean"; then
            echo "$SERVICE_DIR/JustNewsAgent-Clean"; return 0
        fi
    fi

    # Try two levels up from this script (useful when running from repo, not after install)
    local script_dir; script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local candidate; candidate="$(cd "$script_dir/../../.." && pwd)"
    if _is_valid_root "$candidate"; then
        echo "$candidate"; return 0
    fi

    # Final fallback: known path on this machine
    echo "/home/adra/JustNewsAgent-Clean"; return 0
}

PROJECT_ROOT="$(resolve_project_root)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate agent name
validate_agent_name() {
    local agent="$1"

    if [[ -z "$agent" ]]; then
        log_error "Agent name is required"
        log_info "Usage: $SCRIPT_NAME <agent_name>"
        log_info "Available agents: mcp_bus, chief_editor, scout, fact_checker, analyst, synthesizer, critic, memory, reasoning, newsreader, dashboard, analytics, balancer, archive, gpu_orchestrator, crawler, crawler_control"
        exit 1
    fi

    # List of valid agents
    local valid_agents=(
        "mcp_bus"
        "chief_editor"
        "scout"
        "fact_checker"
        "analyst"
        "synthesizer"
        "critic"
        "memory"
        "reasoning"
        "newsreader"
        "dashboard"
        "analytics"
        "balancer"
        "archive"
        "gpu_orchestrator"
        "crawler"
        "crawler_control"
    )

    local agent_valid=false
    for valid_agent in "${valid_agents[@]}"; do
        if [[ "$agent" == "$valid_agent" ]]; then
            agent_valid=true
            break
        fi
    done

    if [[ "$agent_valid" == false ]]; then
        log_error "Invalid agent name: $agent"
        log_info "Valid agents: ${valid_agents[*]}"
        exit 1
    fi
}

# Check if agent directory exists
check_agent_directory() {
    local agent="$1"
    local agent_dir="$PROJECT_ROOT/agents/$agent"

    if [[ ! -d "$agent_dir" ]]; then
        log_error "Agent directory not found: $agent_dir"
        exit 1
    fi

    if [[ ! -f "$agent_dir/main.py" ]]; then
        log_error "Agent main script not found: $agent_dir/main.py"
        exit 1
    fi

    log_success "Agent directory and main script found"
}

# Setup environment
setup_environment() {
    local agent="$1"

    # Change to agent directory
    cd "$PROJECT_ROOT/agents/$agent"

    # Load global environment if available
    if [[ -f "/etc/justnews/global.env" ]]; then
        log_info "Loading global environment from /etc/justnews/global.env"
        set -a
        # shellcheck source=/dev/null
        source "/etc/justnews/global.env"
        set +a
    fi

    # Load agent-specific environment if available
    if [[ -f "/etc/justnews/${agent}.env" ]]; then
        log_info "Loading agent environment from /etc/justnews/${agent}.env"
        set -a
        # shellcheck source=/dev/null
        source "/etc/justnews/${agent}.env"
        set +a
    fi

    # Set default environment variables if not set
    export PYTHONPATH="${PYTHONPATH:-$PROJECT_ROOT}"
    export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

    # Safety mode: force CPU and conservative settings to avoid GPU-related hard resets
    if [[ "${SAFE_MODE:-false}" == "true" ]]; then
        export USE_GPU="false"
        # Disable CUDA visibility entirely for this process
        export CUDA_VISIBLE_DEVICES=""
        # Force CPU execution in libraries that check this flag
        export FORCE_CPU="1"
        # Make tokenizers single-threaded and reduce contention
        export TOKENIZERS_PARALLELISM="false"
        export OMP_NUM_THREADS="1"
        export MKL_NUM_THREADS="1"
        # Conservative PyTorch CUDA allocator config (harmless if CUDA disabled)
        export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True,max_split_size_mb:64,garbage_collection_threshold:0.6"
        # Disable embedding preloading to minimize memory spikes
        export EMBEDDING_PRELOAD_ENABLED="false"
        log_warning "SAFE_MODE enabled: GPU disabled and conservative settings applied"
    else
        # GPU-specific setup
        if [[ "${USE_GPU:-false}" == "true" ]]; then
            export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
            log_info "GPU mode enabled (CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES)"
            # Even with GPU, apply safer allocator defaults
            export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True,max_split_size_mb:128,garbage_collection_threshold:0.8}"
        fi
    fi

    log_success "Environment setup complete"
}

# Wait for dependencies
wait_for_dependencies() {
    local agent="$1"

    # MCP Bus wait: skip for mcp_bus and gpu_orchestrator, or when REQUIRE_BUS=0
    if [[ "${REQUIRE_BUS:-1}" != "0" && "$agent" != "mcp_bus" && "$agent" != "gpu_orchestrator" ]]; then
        log_info "Waiting for MCP Bus dependency..."

        if [[ -x "$PROJECT_ROOT/infrastructure/systemd/scripts/wait_for_mcp.sh" ]]; then
            if ! "$PROJECT_ROOT/infrastructure/systemd/scripts/wait_for_mcp.sh" -q; then
                log_error "Failed to connect to MCP Bus"
                exit 1
            fi
        else
            log_warning "MCP Bus wait script not found, proceeding anyway..."
        fi
    fi

    # Agent-specific dependencies
    case "$agent" in
        "scout")
            # Scout may depend on memory agent
            ;;
        "analyst")
            # Analyst may depend on memory agent
            ;;
        "synthesizer")
            # Synthesizer depends on memory and analyst
            ;;
        "fact_checker")
            # Fact checker may depend on memory
            ;;
        "critic")
            # Critic depends on all analysis agents
            ;;
        "chief_editor")
            # Chief editor depends on all agents
            ;;
    esac

    log_success "Dependency check complete"
}

# Sanity check: ensure runtime python modules exist for this agent before launching.
# This is called from start_agent to produce clearer errors when venvs are misconfigured.
check_python_deps_and_exit_if_missing() {
    local agent="$1"
    # Prefer developer conda env when available (so checks match developer setup)
    local py_cmd=""
    local conda_env_to_try="${CONDA_ENV:-justnews-v2-py312}"
    if command -v conda >/dev/null 2>&1; then
        if conda env list 2>/dev/null | awk '{print $1}' | grep -xq "$conda_env_to_try"; then
            py_cmd="conda run -n $conda_env_to_try python"
        fi
    fi
    if [[ -z "$py_cmd" ]]; then
    local py="${PYTHON_BIN:-/home/adra/miniconda3/envs/justnews-v2-py312/bin/python}"
        if [[ ! -x "$py" ]]; then
            py="$(command -v python3 || command -v python || true)"
        fi
        if [[ -z "$py" ]]; then
            log_warning "No python interpreter available to validate modules; continuing"
            return 0
        fi
        py_cmd="$py"
    fi

    # Modules per agent (keep minimal to avoid import side-effects)
    local modules=(requests)
    if [[ "$agent" == "gpu_orchestrator" ]]; then
        modules=(requests uvicorn)
    fi

    local modules_var="${modules[*]}"
    local missing
    missing=$(eval "$py_cmd - <<PYCODE 2>/dev/null
import importlib, sys
mods = \"${modules_var}\".split()
missing = [m for m in mods if importlib.util.find_spec(m) is None]
sys.stdout.write(' '.join(missing))
PYCODE
")

    if [[ -n "$missing" ]]; then
        log_error "Missing python modules for agent '$agent': $missing"
        if [[ "$py_cmd" == conda* ]]; then
            log_error "Install into the developer conda env (example): conda run -n ${conda_env_to_try} pip install $missing"
        else
            local py_path="$py_cmd"
            py_path="${py_path%% *}"
            log_error "Install them into the service venv (example): sudo ${py_path%/*}/pip install $missing"
        fi
        exit 1
    fi

    # Export the resolved python command so callers can reuse the same interpreter selection
    export SELECTED_PY_CMD="$py_cmd"
}

# Start the agent
start_agent() {
    local agent="$1"

    log_info "Starting $agent agent..."

    # Fail fast with actionable advice if runtime deps are missing in the chosen interpreter
    check_python_deps_and_exit_if_missing "$agent"

    # Build the command - use module invocation to fix relative imports
    # Prefer interpreter from env if provided; reuse the interpreter resolution from dependency check when possible
    local py_interpreter
    if [[ -n "${SELECTED_PY_CMD:-}" ]]; then
        py_interpreter="${SELECTED_PY_CMD}"
    else
        py_interpreter="${PYTHON_BIN:-python3}"
    fi
    if ! command -v $(echo "$py_interpreter" | awk '{print $1}') >/dev/null 2>&1; then
        log_warning "Configured PYTHON_BIN not found (PYTHON_BIN='${PYTHON_BIN:-}'), falling back to 'python3'"
        py_interpreter="python3"
    fi
    local cmd
    if [[ "$agent" == "gpu_orchestrator" ]]; then
        # Prefer uvicorn runner for orchestrator for clearer server logs and binding
        local port="${GPU_ORCHESTRATOR_PORT:-8014}"
        if $py_interpreter -c "import uvicorn" >/dev/null 2>&1; then
            cmd=("$py_interpreter" "-m" "uvicorn" "agents.gpu_orchestrator.main:app" "--host" "0.0.0.0" "--port" "$port" "--log-level" "info")
            log_info "Using uvicorn runner on port $port"
        else
            log_warning "uvicorn not available; falling back to module runner"
            cmd=("$py_interpreter" "-m" "agents.${agent}.main")
        fi
    else
        cmd=("$py_interpreter" "-m" "agents.${agent}.main")
    fi

    # Add any additional arguments from environment
    if [[ -n "${AGENT_ARGS:-}" ]]; then
        # Split AGENT_ARGS into array (simple approach)
        IFS=' ' read -ra ARGS <<< "$AGENT_ARGS"
        cmd+=("${ARGS[@]}")
    fi

    # Log the command (without sensitive info)
    log_info "Using Python: $(command -v "$py_interpreter" || echo "$py_interpreter")"
    log_info "Executing: ${cmd[*]}"

    # Execute the agent
    exec "${cmd[@]}"
}

# Cleanup function
cleanup() {
    local exit_code=$?
    log_info "Agent startup script exiting with code $exit_code"
    exit $exit_code
}

# Show usage
show_usage() {
    cat << EOF
JustNews Agent Startup Script

USAGE:
    $0 <agent_name> [options]

AGENTS:
    mcp_bus         Central communication hub
    chief_editor    Workflow orchestration
    scout           Content discovery
    fact_checker    Fact verification
    analyst         Sentiment analysis
    synthesizer     Content synthesis
    critic          Quality assessment
    memory          Data storage
    reasoning       Logical reasoning
    newsreader      News processing
    dashboard       Web interface
    analytics       System analytics and monitoring
    balancer        Load balancing and resource management
    archive         Content archiving and retrieval
    gpu_orchestrator GPU telemetry and allocation coordinator (SAFE_MODE-aware)
    crawler         Content crawling and data collection
    crawler_control Web interface for crawler management and monitoring

OPTIONS:
    -h, --help      Show this help message

DESCRIPTION:
    Standardized startup script for all JustNews agents.
    Handles environment setup, dependency waiting, and agent execution.

EXAMPLES:
    $0 mcp_bus
    $0 scout
    $0 analyst --gpu

ENVIRONMENT:
    AGENT_ARGS      Additional arguments to pass to the agent
    USE_GPU         Enable GPU mode (default: false)
    CUDA_VISIBLE_DEVICES  GPU device selection

EXIT CODES:
    0 - Success
    1 - Error
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 1 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Main function
main() {
    # Set up cleanup trap
    trap cleanup EXIT

    # Handle help first
    if [[ $# -eq 0 || "$1" == "-h" || "$1" == "--help" ]]; then
        show_usage
        exit 0
    fi

    local agent="$1"
    shift  # Remove agent name from arguments

    # Parse remaining arguments
    parse_args "$@"

    echo "========================================"
    log_info "JustNews Agent Startup: $agent"
    echo "========================================"

    log_info "Resolved PROJECT_ROOT=$PROJECT_ROOT"

    validate_agent_name "$agent"
    check_agent_directory "$agent"
    setup_environment "$agent"
    wait_for_dependencies "$agent"
    start_agent "$agent"
}

# Run main function with all arguments
main "$@"
