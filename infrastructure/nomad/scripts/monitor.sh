#!/bin/bash

# JustNews Nomad Monitoring Script
# This script provides monitoring and health checking for the Nomad deployment

set -e

NOMAD_ADDR="${NOMAD_ADDR:-http://localhost:4646}"
CONSUL_ADDR="${CONSUL_ADDR:-http://localhost:8500}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check Nomad cluster health
check_nomad_health() {
    log_info "Checking Nomad cluster health..."

    # Check server members
    local server_count=$(nomad server members -json | jq '.[] | select(.Status == "alive") | .Name' | wc -l)
    log_info "Nomad servers alive: $server_count"

    # Check client nodes
    local client_count=$(nomad node status -json | jq '.[] | select(.Status == "ready") | .Name' | wc -l)
    log_info "Nomad clients ready: $client_count"

    # Check running jobs
    local job_count=$(nomad job status -json | jq 'length')
    log_info "Running jobs: $job_count"

    # Check allocations
    local healthy_allocs=$(nomad alloc status -json | jq '[.[] | select(.ClientStatus == "running")] | length')
    local total_allocs=$(nomad alloc status -json | jq 'length')
    log_info "Healthy allocations: $healthy_allocs/$total_allocs"

    if [ "$healthy_allocs" -eq "$total_allocs" ] && [ "$total_allocs" -gt 0 ]; then
        log_success "Nomad cluster is healthy"
    else
        log_warning "Nomad cluster has issues"
    fi
}

# Check Consul health
check_consul_health() {
    log_info "Checking Consul cluster health..."

    # Check leader
    local leader=$(curl -s "$CONSUL_ADDR/v1/status/leader" | tr -d '"')
    if [ -n "$leader" ]; then
        log_success "Consul leader: $leader"
    else
        log_error "No Consul leader found"
        return 1
    fi

    # Check services
    local service_count=$(curl -s "$CONSUL_ADDR/v1/catalog/services" | jq 'length')
    log_info "Registered services: $service_count"

    # Check nodes
    local node_count=$(curl -s "$CONSUL_ADDR/v1/catalog/nodes" | jq 'length')
    log_info "Consul nodes: $node_count"
}

# Check service health
check_service_health() {
    log_info "Checking JustNews service health..."

    # List of expected services
    local expected_services=("postgres" "redis" "prometheus" "grafana" "mcp-bus" "scout" "memory" "reasoning" "balancer" "analyst" "synthesizer" "fact-checker" "newsreader")

    for service in "${expected_services[@]}"; do
        local instances=$(curl -s "$CONSUL_ADDR/v1/health/service/$service" | jq '[.[] | select(.Checks[]?.Status == "passing")] | length')
        if [ "$instances" -gt 0 ]; then
            echo -e "  ${GREEN}✓${NC} $service: $instances healthy instances"
        else
            echo -e "  ${RED}✗${NC} $service: no healthy instances"
        fi
    done
}

# Check resource usage
check_resources() {
    log_info "Checking resource usage..."

    # CPU usage
    nomad operator metrics | grep -A 5 "nomad.runtime.cpu"

    # Memory usage
    nomad operator metrics | grep -A 5 "nomad.runtime.memory"

    # Disk usage
    df -h /opt/nomad/data 2>/dev/null || log_warning "Cannot check disk usage"
}

# Check GPU resources (if available)
check_gpu_resources() {
    log_info "Checking GPU resources..."

    # Check for GPU nodes
    local gpu_nodes=$(nomad node status -json | jq '[.[] | select(.Attributes["unique.platform.aws.instance-type"]? or (.Attributes["gpu.count"]? > 0))] | length')

    if [ "$gpu_nodes" -gt 0 ]; then
        log_info "GPU nodes detected: $gpu_nodes"

        # Check GPU allocations
        nomad alloc status -json | jq -r '.[] | select(.Resources.Devices[]?.Name == "nvidia.com/gpu") | "\(.Name): \(.Resources.Devices[]?.Count) GPUs"'
    else
        log_info "No GPU nodes detected"
    fi
}

# Generate health report
generate_report() {
    local report_file="health_report_$(date +%Y%m%d_%H%M%S).txt"

    log_info "Generating health report: $report_file"

    {
        echo "JustNews Nomad Health Report"
        echo "Generated: $(date)"
        echo "================================="
        echo
    } > "$report_file"

    # Nomad status
    echo "Nomad Cluster Status:" >> "$report_file"
    nomad server members >> "$report_file" 2>/dev/null || echo "Unable to get server members" >> "$report_file"
    echo >> "$report_file"

    # Job status
    echo "Job Status:" >> "$report_file"
    nomad job status >> "$report_file" 2>/dev/null || echo "Unable to get job status" >> "$report_file"
    echo >> "$report_file"

    # Allocation status
    echo "Allocation Status:" >> "$report_file"
    nomad alloc status | head -20 >> "$report_file" 2>/dev/null || echo "Unable to get allocation status" >> "$report_file"
    echo >> "$report_file"

    # Consul services
    echo "Consul Services:" >> "$report_file"
    curl -s "$CONSUL_ADDR/v1/catalog/services" | jq -r 'keys[]' | sort >> "$report_file" 2>/dev/null || echo "Unable to get services" >> "$report_file"
    echo >> "$report_file"

    log_success "Health report saved to $report_file"
}

# Show usage
usage() {
    cat << EOF
JustNews Nomad Monitoring Script

Usage: $0 [COMMAND]

Commands:
    health          Check overall cluster health
    services        Check service health status
    resources       Check resource usage
    gpu             Check GPU resource status
    report          Generate detailed health report
    all             Run all checks
    help            Show this help

Environment Variables:
    NOMAD_ADDR      Nomad server address (default: http://localhost:4646)
    CONSUL_ADDR     Consul server address (default: http://localhost:8500)

Examples:
    $0 health
    $0 all
    $0 report

EOF
}

# Main command handling
case "${1:-help}" in
    health)
        check_nomad_health
        check_consul_health
        ;;
    services)
        check_service_health
        ;;
    resources)
        check_resources
        ;;
    gpu)
        check_gpu_resources
        ;;
    report)
        generate_report
        ;;
    all)
        check_nomad_health
        echo
        check_consul_health
        echo
        check_service_health
        echo
        check_resources
        echo
        check_gpu_resources
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        log_error "Unknown command: $1"
        usage
        exit 1
        ;;
esac