#!/bin/bash
# Unified Deployment Script for JustNews
# Supports Docker Compose, Kubernetes, and systemd deployments

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

# Help function
show_help() {
    cat << EOF
JustNews Unified Deployment Script

USAGE:
    $0 [OPTIONS] [COMMAND]

COMMANDS:
    deploy          Deploy services to target platform
    status          Show deployment status
    health          Run health checks
    rollback        Rollback deployment
    cleanup         Clean up deployment artifacts

OPTIONS:
    -t, --target TARGET    Deployment target (docker-compose, kubernetes, systemd)
    -e, --env ENV          Environment (development, staging, production)
    -s, --service SERVICE  Specific service to deploy
    -f, --force            Force deployment (skip checks)
    -v, --verbose          Verbose output
    -h, --help            Show this help

EXAMPLES:
    # Deploy to Docker Compose (development)
    $0 --target docker-compose --env development deploy

    # Deploy to Kubernetes (production)
    $0 --target kubernetes --env production deploy

    # Deploy specific service
    $0 --target kubernetes --service mcp-bus deploy

    # Check deployment status
    $0 --target kubernetes status

    # Run health checks
    $0 health

    # Rollback deployment
    $0 --target kubernetes rollback

ENVIRONMENT VARIABLES:
    DEPLOY_TARGET          Default deployment target
    DEPLOY_ENV            Default environment
    FORCE_DEPLOY          Force deployment (1=yes, 0=no)
    VERBOSE               Verbose output (1=yes, 0=no)

EOF
}

# Parse command line arguments
parse_args() {
    TARGET="${DEPLOY_TARGET:-docker-compose}"
    ENV="${DEPLOY_ENV:-development}"
    SERVICE=""
    FORCE="${FORCE_DEPLOY:-0}"
    VERBOSE="${VERBOSE:-0}"
    COMMAND=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--target)
                TARGET="$2"
                shift 2
                ;;
            -e|--env)
                ENV="$2"
                shift 2
                ;;
            -s|--service)
                SERVICE="$2"
                shift 2
                ;;
            -f|--force)
                FORCE=1
                shift
                ;;
            -v|--verbose)
                VERBOSE=1
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            deploy|status|health|rollback|cleanup)
                COMMAND="$1"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Default command
    if [[ -z "$COMMAND" ]]; then
        COMMAND="deploy"
    fi
}

# Validate environment
validate_environment() {
    log_info "Validating environment..."

    # Check if we're in the right directory
    if [[ ! -f "$PROJECT_ROOT/requirements.txt" ]]; then
        log_error "Not in JustNews project root directory"
        exit 1
    fi

    # Check target platform
    case $TARGET in
        docker-compose)
            if ! command -v docker &> /dev/null; then
                log_error "Docker is not installed"
                exit 1
            fi
            if ! command -v docker-compose &> /dev/null; then
                log_error "Docker Compose is not installed"
                exit 1
            fi
            ;;
        kubernetes)
            if ! command -v kubectl &> /dev/null; then
                log_error "kubectl is not installed"
                exit 1
            fi
            ;;
        systemd)
            if ! command -v systemctl &> /dev/null; then
                log_error "systemctl is not available"
                exit 1
            fi
            ;;
        *)
            log_error "Unsupported target: $TARGET"
            exit 1
            ;;
    esac

    # Check environment configuration
    ENV_FILE="$DEPLOY_ROOT/config/environments/${ENV}.env"
    if [[ ! -f "$ENV_FILE" ]]; then
        log_warning "Environment file not found: $ENV_FILE"
        log_info "Creating default environment file..."
        create_default_env
    fi

    log_success "Environment validation passed"
}

# Create default environment file
create_default_env() {
    mkdir -p "$DEPLOY_ROOT/config/environments"

    cat > "$DEPLOY_ROOT/config/environments/${ENV}.env" << EOF
# JustNews Environment Configuration
# Generated for environment: $ENV

# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=justnews
POSTGRES_USER=justnews
POSTGRES_PASSWORD=change_me_in_production

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# GPU Configuration
GPU_ORCHESTRATOR_HOST=localhost
GPU_ORCHESTRATOR_PORT=8014
CUDA_VISIBLE_DEVICES=0

# MCP Bus Configuration
MCP_BUS_HOST=localhost
MCP_BUS_PORT=8000

# Monitoring Configuration
GRAFANA_ADMIN_PASSWORD=admin
PROMETHEUS_RETENTION_TIME=30d
LOG_LEVEL=INFO
LOG_FORMAT=json

# Security Configuration
SECRET_KEY=change_me_in_production
JWT_SECRET_KEY=change_me_in_production

# Service Configuration
DEPLOY_ENV=$ENV
DEPLOY_TARGET=$TARGET
EOF

    log_success "Created default environment file: $ENV_FILE"
    log_warning "Please customize the configuration before deployment"
}

# Deploy to Docker Compose
deploy_docker_compose() {
    log_info "Deploying to Docker Compose..."

    cd "$DEPLOY_ROOT/docker"

    # Build images if needed
    if [[ "$FORCE" == "1" ]] || [[ ! -f ".built" ]]; then
        log_info "Building Docker images..."
        docker-compose build
        touch .built
    fi

    # Start services
    COMPOSE_FILES="-f docker-compose.yml"
    if [[ -f "docker-compose.${ENV}.yml" ]]; then
        COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.${ENV}.yml"
    fi

    if [[ -n "$SERVICE" ]]; then
        log_info "Starting service: $SERVICE"
        docker-compose $COMPOSE_FILES up -d "$SERVICE"
    else
        log_info "Starting all services..."
        docker-compose $COMPOSE_FILES up -d
    fi

    log_success "Docker Compose deployment completed"
}

# Deploy to Kubernetes
deploy_kubernetes() {
    log_info "Deploying to Kubernetes..."

    cd "$DEPLOY_ROOT/kubernetes"

    # Apply manifests
    if [[ -n "$SERVICE" ]]; then
        log_info "Deploying service: $SERVICE"
        kubectl apply -f "base/${SERVICE}.yml"
        if [[ -f "overlays/${ENV}/${SERVICE}.yml" ]]; then
            kubectl apply -f "overlays/${ENV}/${SERVICE}.yml"
        fi
    else
        log_info "Deploying all services..."
        kubectl apply -k .
    fi

    # Wait for rollout
    if [[ -n "$SERVICE" ]]; then
        kubectl rollout status deployment/"$SERVICE"
    else
        # Wait for all deployments
        kubectl wait --for=condition=available --timeout=300s deployment --all
    fi

    log_success "Kubernetes deployment completed"
}

# Deploy to systemd
deploy_systemd() {
    log_info "Deploying to systemd..."

    cd "$DEPLOY_ROOT/systemd"

    # Install service files
    sudo cp services/*.service /etc/systemd/system/
    sudo cp timers/*.timer /etc/systemd/system/ 2>/dev/null || true
    sudo systemctl daemon-reload

    # Start services
    if [[ -n "$SERVICE" ]]; then
        log_info "Starting service: $SERVICE"
        sudo systemctl enable "justnews-${SERVICE}.service"
        sudo systemctl start "justnews-${SERVICE}.service"
    else
        log_info "Starting all services..."
        for service in services/*.service; do
            service_name=$(basename "$service" .service)
            sudo systemctl enable "$service_name"
            sudo systemctl start "$service_name"
        done
    fi

    log_success "Systemd deployment completed"
}

# Show deployment status
show_status() {
    log_info "Checking deployment status..."

    case $TARGET in
        docker-compose)
            cd "$DEPLOY_ROOT/docker"
            docker-compose ps
            ;;
        kubernetes)
            kubectl get pods,services,deployments -l app=justnews
            ;;
        systemd)
            systemctl list-units --type=service --state=active | grep justnews
            ;;
    esac
}

# Run health checks
run_health_checks() {
    log_info "Running health checks..."

    # Run the health check script
    if [[ -f "$DEPLOY_ROOT/scripts/health-check.sh" ]]; then
        bash "$DEPLOY_ROOT/scripts/health-check.sh"
    else
        log_warning "Health check script not found"
        # Basic health checks
        case $TARGET in
            docker-compose)
                cd "$DEPLOY_ROOT/docker"
                docker-compose ps | grep -E "(Up|running)"
                ;;
            kubernetes)
                kubectl get pods -l app=justnews --no-headers | grep -v Running || true
                ;;
            systemd)
                systemctl is-active justnews-mcp-bus || true
                ;;
        esac
    fi
}

# Rollback deployment
rollback_deployment() {
    log_info "Rolling back deployment..."

    case $TARGET in
        docker-compose)
            cd "$DEPLOY_ROOT/docker"
            docker-compose down
            docker-compose pull  # Get previous images
            docker-compose up -d
            ;;
        kubernetes)
            if [[ -n "$SERVICE" ]]; then
                kubectl rollout undo deployment/"$SERVICE"
            else
                # Rollback all deployments
                for deployment in $(kubectl get deployments -l app=justnews -o jsonpath='{.items[*].metadata.name}'); do
                    kubectl rollout undo deployment/"$deployment"
                done
            fi
            ;;
        systemd)
            log_warning "Systemd rollback not implemented - manual intervention required"
            ;;
    esac

    log_success "Rollback completed"
}

# Cleanup deployment
cleanup_deployment() {
    log_info "Cleaning up deployment..."

    case $TARGET in
        docker-compose)
            cd "$DEPLOY_ROOT/docker"
            docker-compose down -v --remove-orphans
            docker system prune -f
            rm -f .built
            ;;
        kubernetes)
            kubectl delete -k "$DEPLOY_ROOT/kubernetes" --ignore-not-found=true
            ;;
        systemd)
            for service in /etc/systemd/system/justnews-*.service; do
                sudo systemctl stop "$(basename "$service")" || true
                sudo systemctl disable "$(basename "$service")" || true
                sudo rm -f "$service"
            done
            sudo systemctl daemon-reload
            ;;
    esac

    log_success "Cleanup completed"
}

# Main deployment function
main() {
    parse_args "$@"

    if [[ "$VERBOSE" == "1" ]]; then
        set -x
    fi

    log_info "JustNews Deployment Script"
    log_info "Target: $TARGET"
    log_info "Environment: $ENV"
    log_info "Command: $COMMAND"

    case $COMMAND in
        deploy)
            validate_environment
            case $TARGET in
                docker-compose)
                    deploy_docker_compose
                    ;;
                kubernetes)
                    deploy_kubernetes
                    ;;
                systemd)
                    deploy_systemd
                    ;;
            esac
            run_health_checks
            ;;
        status)
            show_status
            ;;
        health)
            run_health_checks
            ;;
        rollback)
            rollback_deployment
            ;;
        cleanup)
            cleanup_deployment
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            show_help
            exit 1
            ;;
    esac

    log_success "Deployment operation completed successfully"
}

# Run main function
main "$@"</content>
<parameter name="filePath">/home/adra/JustNewsAgent/deploy/refactor/scripts/deploy.sh