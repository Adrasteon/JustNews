#!/bin/bash
# enable_all.sh - JustNews systemd service management script
# Enables, disables, starts, and stops all JustNews services in proper order

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Service definitions in startup order
SERVICES=(
    "gpu_orchestrator" # GPU Orchestrator (port 8014) — MUST start before mcp_bus
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
    "balancer"
    "analytics"      # Analytics service (port 8011 per canonical mapping)
    "archive"        # Archive agent (port 8012)
    "dashboard"      # Dashboard agent (port 8013)
    "crawler"        # Unified Production Crawler - intelligent multi-strategy
    "crawler_control" # Crawler Control web interface (port 8016)
)

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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (sudo)"
        exit 1
    fi
}

# Check if systemctl is available
check_systemctl() {
    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl not found. This script requires systemd."
        exit 1
    fi
}

# Check if services are installed
check_services_installed() {
    # Check for systemd template file instead of individual service files
    if [[ ! -f "/etc/systemd/system/justnews@.service" ]]; then
        log_error "Missing systemd service template file"
        log_error "Please install the systemd unit template first:"
        log_error "  sudo cp $PROJECT_ROOT/deploy/systemd/units/justnews@.service /etc/systemd/system/"
        log_error "  sudo systemctl daemon-reload"
        exit 1
    fi

    # Check for required scripts
    if [[ ! -f "/usr/local/bin/justnews-start-agent.sh" ]]; then
        log_error "Missing justnews-start-agent.sh script"
        log_error "Please install the startup script:"
    log_error "  sudo cp $PROJECT_ROOT/deploy/systemd/justnews-start-agent.sh /usr/local/bin/"
        log_error "  sudo chmod +x /usr/local/bin/justnews-start-agent.sh"
        exit 1
    fi

    if [[ ! -f "/usr/local/bin/wait_for_mcp.sh" ]]; then
        log_error "Missing wait_for_mcp.sh script"
        log_error "Please install the MCP wait script:"
    log_error "  sudo cp $PROJECT_ROOT/deploy/systemd/wait_for_mcp.sh /usr/local/bin/"
        log_error "  sudo chmod +x /usr/local/bin/wait_for_mcp.sh"
        exit 1
    fi
}

# Ensure operator PATH wrappers exist (best-effort, idempotent)
ensure_path_wrappers() {
    local pairs=(
        "/usr/local/bin/enable_all.sh|$PROJECT_ROOT/deploy/systemd/scripts/enable_all.sh"
        "/usr/local/bin/health_check.sh|$PROJECT_ROOT/deploy/systemd/scripts/health_check.sh"
    )
    for pair in "${pairs[@]}"; do
        IFS='|' read -r dst src <<<"$pair"
        if [[ -f "$src" && ! -x "$dst" ]]; then
            cp "$src" "$dst" && chmod +x "$dst" || true
        fi
    done
}

# Wait for service to be ready
wait_for_service() {
    local service="$1"
    local timeout="${2:-30}"
    local count=0

    log_info "Waiting for $service to be ready..."

    while [[ $count -lt $timeout ]]; do
        if systemctl is-active --quiet "justnews@${service}"; then
            log_success "$service is ready"
            return 0
        fi

        sleep 1
        ((count++))
    done

    log_warning "$service did not become ready within $timeout seconds"
    return 1
}

# Wait for an HTTP endpoint to become healthy
wait_for_http() {
    local url="$1"
    local timeout="${2:-30}"
    local count=0

    while [[ $count -lt $timeout ]]; do
        if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        ((count++))
    done
    return 1
}

# Enable services
enable_services() {
    log_info "Enabling JustNews services..."

    for service in "${SERVICES[@]}"; do
        log_info "Enabling justnews@${service}..."
        systemctl enable "justnews@${service}" 2>/dev/null || true
    done

    log_success "All services enabled"
}

# Disable services
disable_services() {
    log_info "Disabling JustNews services..."

    for service in "${SERVICES[@]}"; do
        log_info "Disabling justnews@${service}..."
        systemctl disable "justnews@${service}" 2>/dev/null || true
    done

    log_success "All services disabled"
}

# Start services in order
start_services() {
    log_info "Starting JustNews services in order..."

    # 1) GPU Orchestrator first
    log_info "Starting GPU Orchestrator (justnews@gpu_orchestrator)..."
    systemctl start "justnews@gpu_orchestrator"
    if ! wait_for_service "gpu_orchestrator" 60; then
        log_error "gpu_orchestrator did not become active in time. Aborting."
        return 1
    fi
    if ! wait_for_http "http://127.0.0.1:8014/ready" 120; then
        log_warning "gpu_orchestrator READY endpoint not ready within timeout; continuing cautiously"
    else
        log_success "gpu_orchestrator reports READY"
    fi
    
    # 2) MCP Bus next
    log_info "Starting MCP Bus (justnews@mcp_bus)..."
    systemctl start "justnews@mcp_bus"
    if ! wait_for_service "mcp_bus" 30; then
        log_error "MCP Bus failed to start. Aborting."
        return 1
    fi
    if ! wait_for_http "http://127.0.0.1:8000/health" 30; then
        log_warning "MCP Bus HTTP health not ready within timeout"
    fi

    # 3) Start remaining services
    for service in "${SERVICES[@]:2}"; do
        log_info "Starting justnews@${service}..."
        systemctl start "justnews@${service}"
        sleep 2
    done

    log_success "All services started"
}

# Stop services in reverse order
stop_services() {
    log_info "Stopping JustNews services..."

    # Stop in reverse order (dependencies first)
    for ((i=${#SERVICES[@]}-1; i>=0; i--)); do
        service="${SERVICES[i]}"
        log_info "Stopping justnews@${service}..."
        systemctl stop "justnews@${service}" 2>/dev/null || true
    done

    log_success "All services stopped"
}

# Restart all services
restart_services() {
    log_info "Restarting all JustNews services..."
    stop_services
    sleep 3
    start_services
}

# Show status of all services
show_status() {
    echo
    log_info "JustNews Service Status:"
    echo "=========================="

    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "justnews@${service}"; then
            echo -e "${GREEN}●${NC} justnews@${service} - Active"
        elif systemctl is-failed --quiet "justnews@${service}"; then
            echo -e "${RED}●${NC} justnews@${service} - Failed"
        else
            echo -e "${YELLOW}●${NC} justnews@${service} - Inactive"
        fi
    done
    echo
}

# Fresh start (stop, disable, enable, start)
fresh_start() {
    log_info "Performing fresh start of all services..."

    # Stop all services
    stop_services
    sleep 2

    # Disable all services
    disable_services
    sleep 2

    # Enable all services
    enable_services
    sleep 2

    # Start all services
    start_services

    log_success "Fresh start completed"
}

# Main function
main() {
    local action="${1:-status}"
    # Backward-compat alias: allow "--fresh" as synonym for "fresh"
    if [[ "$action" == "--fresh" ]]; then
        action="fresh"
    fi

    check_root
    check_systemctl
    check_services_installed
    ensure_path_wrappers

    case "$action" in
        "enable")
            enable_services
            ;;
        "disable")
            disable_services
            ;;
        "start")
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "status")
            show_status
            ;;
        "fresh")
            fresh_start
            ;;
        *)
            log_error "Usage: $0 {enable|disable|start|stop|restart|status|fresh|--fresh} [services...]"
            log_info "Commands:"
            log_info "  enable   - Enable all services"
            log_info "  disable  - Disable all services"
            log_info "  start    - Start all services in order"
            log_info "  stop     - Stop all services"
            log_info "  restart  - Restart all services"
            log_info "  status   - Show status of all services"
            log_info "  fresh    - Fresh start (stop→disable→enable→start)"
            log_info "  --fresh  - Alias of 'fresh' (backward compatible)"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
