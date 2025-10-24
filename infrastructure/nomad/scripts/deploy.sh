#!/bin/bash

# JustNews Nomad Deployment Script
# This script manages the complete Nomad deployment lifecycle

set -e

# Configuration
NOMAD_ADDR="${NOMAD_ADDR:-http://localhost:4646}"
CONSUL_ADDR="${CONSUL_ADDR:-http://localhost:8500}"
JOBS_DIR="./jobs"

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

# Check if Nomad is available
check_nomad() {
    if ! command -v nomad &> /dev/null; then
        log_error "Nomad CLI is not installed"
        exit 1
    fi

    if ! nomad server members &> /dev/null; then
        log_error "Cannot connect to Nomad cluster at $NOMAD_ADDR"
        log_info "Make sure NOMAD_ADDR is set correctly and the cluster is running"
        exit 1
    fi

    log_success "Nomad cluster is accessible"
}

# Check if Consul is available
check_consul() {
    if ! curl -s "$CONSUL_ADDR/v1/status/leader" &> /dev/null; then
        log_error "Cannot connect to Consul at $CONSUL_ADDR"
        log_info "Make sure Consul is running and accessible"
        exit 1
    fi

    log_success "Consul is accessible"
}

# Deploy infrastructure services
deploy_infrastructure() {
    log_info "Deploying infrastructure services..."

    nomad job run "$JOBS_DIR/infrastructure.nomad"

    log_success "Infrastructure services deployed"
}

# Deploy AI agents
deploy_agents() {
    log_info "Deploying AI agents..."

    nomad job run "$JOBS_DIR/agents.nomad"

    log_success "AI agents deployed"
}

# Check deployment status
check_deployment() {
    log_info "Checking deployment status..."

    # Check infrastructure jobs
    log_info "Infrastructure services:"
    nomad job status | grep -E "(justnews-infrastructure|infrastructure)" | while read -r line; do
        echo "  $line"
    done

    # Check agent jobs
    log_info "AI agents:"
    nomad job status | grep -E "(justnews-agents|agents)" | while read -r line; do
        echo "  $line"
    done

    # Check allocations
    log_info "Recent allocations:"
    nomad alloc status | head -10
}

# Stop all jobs
stop_deployment() {
    log_info "Stopping all JustNews jobs..."

    # Stop agent jobs
    nomad job stop -purge justnews-agents || true
    nomad job stop -purge justnews-infrastructure || true

    log_success "All jobs stopped"
}

# Scale a job
scale_job() {
    local job_name="$1"
    local count="$2"

    if [ -z "$job_name" ] || [ -z "$count" ]; then
        log_error "Usage: scale <job-name> <count>"
        exit 1
    fi

    log_info "Scaling $job_name to $count instances..."

    nomad job scale "$job_name" "$count"

    log_success "Job scaled successfully"
}

# Get job logs
get_logs() {
    local job_name="$1"
    local task_name="${2:-}"

    if [ -z "$job_name" ]; then
        log_error "Usage: logs <job-name> [task-name]"
        exit 1
    fi

    if [ -n "$task_name" ]; then
        nomad alloc logs -job "$job_name" -task "$task_name" -f
    else
        nomad alloc logs -job "$job_name" -f
    fi
}

# Update job
update_job() {
    local job_name="$1"

    if [ -z "$job_name" ]; then
        log_error "Usage: update <job-name>"
        exit 1
    fi

    log_info "Updating job $job_name..."

    nomad job run "$JOBS_DIR/${job_name}.nomad"

    log_success "Job updated successfully"
}

# Show cluster status
show_status() {
    log_info "Nomad Cluster Status:"
    echo "======================"
    nomad server members
    echo
    log_info "Nomad Nodes:"
    nomad node status
    echo
    log_info "Running Jobs:"
    nomad job status
    echo
    log_info "Consul Services:"
    curl -s "$CONSUL_ADDR/v1/catalog/services" | jq -r 'keys[]' | sort
}

# Show usage
usage() {
    cat << EOF
JustNews Nomad Deployment Script

Usage: $0 [COMMAND]

Commands:
    check           Check Nomad and Consul connectivity
    deploy          Deploy all services (infrastructure + agents)
    deploy-infra    Deploy only infrastructure services
    deploy-agents   Deploy only AI agents
    status          Show deployment status
    stop            Stop all jobs
    scale           Scale a job (usage: scale <job-name> <count>)
    logs            Show logs for a job (usage: logs <job-name> [task-name])
    update          Update a job (usage: update <job-name>)
    cluster-status  Show cluster status
    help            Show this help

Environment Variables:
    NOMAD_ADDR      Nomad server address (default: http://localhost:4646)
    CONSUL_ADDR     Consul server address (default: http://localhost:8500)

Examples:
    $0 check
    $0 deploy
    $0 scale justnews-agents 5
    $0 logs justnews-infrastructure postgres
    $0 status

EOF
}

# Main command handling
case "${1:-help}" in
    check)
        check_nomad
        check_consul
        ;;
    deploy)
        check_nomad
        check_consul
        deploy_infrastructure
        sleep 30  # Wait for infrastructure to be ready
        deploy_agents
        check_deployment
        ;;
    deploy-infra)
        check_nomad
        check_consul
        deploy_infrastructure
        check_deployment
        ;;
    deploy-agents)
        check_nomad
        check_consul
        deploy_agents
        check_deployment
        ;;
    status)
        check_nomad
        check_deployment
        ;;
    stop)
        check_nomad
        stop_deployment
        ;;
    scale)
        check_nomad
        scale_job "$2" "$3"
        ;;
    logs)
        check_nomad
        get_logs "$2" "$3"
        ;;
    update)
        check_nomad
        update_job "$2"
        ;;
    cluster-status)
        check_nomad
        show_status
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