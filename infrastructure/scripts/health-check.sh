#!/bin/bash
# Health Check Script for JustNewsAgent
# Validates deployment health across all platforms

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_ROOT="$PROJECT_ROOT/deploy/refactor"

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

# Global health status
HEALTH_STATUS="healthy"
FAILED_CHECKS=()

# Add failed check
add_failure() {
    FAILED_CHECKS+=("$1")
    HEALTH_STATUS="unhealthy"
}

# Service definitions
SERVICES=(
    "mcp-bus:8000"
    "chief-editor:8001"
    "scout:8002"
    "fact-checker:8003"
    "analyst:8004"
    "synthesizer:8005"
    "critic:8006"
    "memory:8007"
    "reasoning:8008"
    "gpu-orchestrator:8014"
    "dashboard:8013"
)

# Check service health
check_service() {
    local service=$1
    local port=$2
    local name="${service//-/_}"

    log_info "Checking $service on port $port..."

    # Try to connect to the service
    if timeout 10 bash -c "echo > /dev/tcp/localhost/$port" 2>/dev/null; then
        # Try health endpoint if available
        if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
            log_success "$service is healthy"
            return 0
        elif curl -s -f "http://localhost:$port/" >/dev/null 2>&1; then
            log_success "$service is responding"
            return 0
        else
            log_warning "$service port open but no health endpoint"
            return 0
        fi
    else
        log_error "$service is not responding on port $port"
        add_failure "$service:port_$port"
        return 1
    fi
}

# Check Docker Compose health
check_docker_compose() {
    log_info "Checking Docker Compose deployment..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker not available"
        add_failure "docker:unavailable"
        return 1
    fi

    cd "$DEPLOY_ROOT/docker"

    # Check if services are running
    local running_services
    running_services=$(docker-compose ps --services --filter "status=running" | wc -l)

    if [[ $running_services -eq 0 ]]; then
        log_error "No Docker Compose services are running"
        add_failure "docker-compose:no_services"
        return 1
    fi

    log_success "Docker Compose: $running_services services running"

    # Check individual containers
    while IFS= read -r line; do
        if [[ $line =~ ([a-z-]+)_([0-9]+)[[:space:]]+Up ]]; then
            local service="${BASH_REMATCH[1]}"
            log_success "Container $service is running"
        fi
    done < <(docker-compose ps)

    return 0
}

# Check Kubernetes health
check_kubernetes() {
    log_info "Checking Kubernetes deployment..."

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not available"
        add_failure "kubectl:unavailable"
        return 1
    fi

    # Check if cluster is accessible
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Kubernetes cluster not accessible"
        add_failure "kubernetes:cluster_inaccessible"
        return 1
    fi

    # Check pods
    local unhealthy_pods
    unhealthy_pods=$(kubectl get pods -l app=justnews --no-headers 2>/dev/null | grep -v Running | wc -l)

    if [[ $unhealthy_pods -gt 0 ]]; then
        log_error "Found $unhealthy_pods unhealthy pods"
        kubectl get pods -l app=justnews --no-headers | grep -v Running | while read -r line; do
            local pod_name=$(echo "$line" | awk '{print $1}')
            local status=$(echo "$line" | awk '{print $3}')
            add_failure "kubernetes:pod_${pod_name}_${status}"
        done
        return 1
    fi

    local total_pods
    total_pods=$(kubectl get pods -l app=justnews --no-headers 2>/dev/null | wc -l)

    log_success "Kubernetes: $total_pods pods healthy"

    return 0
}

# Check systemd health
check_systemd() {
    log_info "Checking systemd deployment..."

    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl not available"
        add_failure "systemctl:unavailable"
        return 1
    fi

    local failed_services=0

    for service in /etc/systemd/system/justnews-*.service; do
        if [[ -f "$service" ]]; then
            local service_name=$(basename "$service")
            if ! systemctl is-active "$service_name" >/dev/null 2>&1; then
                log_error "Service $service_name is not active"
                add_failure "systemd:service_${service_name}"
                ((failed_services++))
            else
                log_success "Service $service_name is active"
            fi
        fi
    done

    if [[ $failed_services -gt 0 ]]; then
        return 1
    fi

    return 0
}

# Check database connectivity
check_database() {
    log_info "Checking database connectivity..."

    # Try to connect to PostgreSQL
    if command -v psql &> /dev/null; then
        if PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" \
            -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-justnews}" \
            -d "${POSTGRES_DB:-justnews}" -c "SELECT 1;" >/dev/null 2>&1; then
            log_success "Database connection successful"
            return 0
        fi
    fi

    # Try via MCP Bus if available
    if curl -s -f "http://localhost:8000/health" >/dev/null 2>&1; then
        local db_status
        db_status=$(curl -s "http://localhost:8000/health" | jq -r '.database' 2>/dev/null || echo "unknown")
        if [[ "$db_status" == "healthy" ]]; then
            log_success "Database healthy via MCP Bus"
            return 0
        fi
    fi

    log_error "Database connection failed"
    add_failure "database:connection_failed"
    return 1
}

# Check Redis connectivity
check_redis() {
    log_info "Checking Redis connectivity..."

    if command -v redis-cli &> /dev/null; then
        if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" \
            ${REDIS_PASSWORD:+-a "$REDIS_PASSWORD"} ping >/dev/null 2>&1; then
            log_success "Redis connection successful"
            return 0
        fi
    fi

    log_error "Redis connection failed"
    add_failure "redis:connection_failed"
    return 1
}

# Check GPU availability
check_gpu() {
    log_info "Checking GPU availability..."

    if command -v nvidia-smi &> /dev/null; then
        local gpu_count
        gpu_count=$(nvidia-smi --list-gpus 2>/dev/null | wc -l)
        if [[ $gpu_count -gt 0 ]]; then
            log_success "GPU available: $gpu_count device(s)"
            return 0
        fi
    fi

    # Check if GPU orchestrator is available
    if curl -s -f "http://localhost:8014/health" >/dev/null 2>&1; then
        log_success "GPU orchestrator available"
        return 0
    fi

    log_warning "No GPU available - using CPU fallback"
    return 0
}

# Check monitoring stack
check_monitoring() {
    log_info "Checking monitoring stack..."

    # Check Prometheus
    if curl -s -f "http://localhost:9090/-/healthy" >/dev/null 2>&1; then
        log_success "Prometheus is healthy"
    else
        log_warning "Prometheus not available"
    fi

    # Check Grafana
    if curl -s -f "http://localhost:3000/api/health" >/dev/null 2>&1; then
        log_success "Grafana is healthy"
    else
        log_warning "Grafana not available"
    fi
}

# Generate health report
generate_report() {
    log_info "Generating health report..."

    local report_file="$DEPLOY_ROOT/health-report-$(date +%Y%m%d-%H%M%S).json"

    cat > "$report_file" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "overall_status": "$HEALTH_STATUS",
  "failed_checks": $(printf '%s\n' "${FAILED_CHECKS[@]}" | jq -R . | jq -s .),
  "services_checked": $(printf '%s\n' "${SERVICES[@]}" | jq -R . | jq -s .),
  "platform": "$TARGET",
  "environment": "$ENV"
}
EOF

    log_info "Health report saved to: $report_file"

    if [[ "$HEALTH_STATUS" == "healthy" ]]; then
        log_success "All health checks passed!"
        return 0
    else
        log_error "Health check failures detected:"
        printf '  - %s\n' "${FAILED_CHECKS[@]}"
        return 1
    fi
}

# Main health check function
main() {
    local TARGET="${DEPLOY_TARGET:-docker-compose}"
    local ENV="${DEPLOY_ENV:-development}"

    log_info "JustNewsAgent Health Check"
    log_info "Platform: $TARGET"
    log_info "Environment: $ENV"

    # Load environment variables
    ENV_FILE="$DEPLOY_ROOT/config/environments/${ENV}.env"
    if [[ -f "$ENV_FILE" ]]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi

    # Platform-specific checks
    case $TARGET in
        docker-compose)
            check_docker_compose
            ;;
        kubernetes)
            check_kubernetes
            ;;
        systemd)
            check_systemd
            ;;
    esac

    # Common checks
    check_database
    check_redis
    check_gpu
    check_monitoring

    # Service-specific checks
    for service_port in "${SERVICES[@]}"; do
        IFS=':' read -r service port <<< "$service_port"
        check_service "$service" "$port"
    done

    # Generate report
    generate_report
}

# Run main function
main "$@"</content>
<parameter name="filePath">/home/adra/JustNewsAgent/deploy/refactor/scripts/health-check.sh