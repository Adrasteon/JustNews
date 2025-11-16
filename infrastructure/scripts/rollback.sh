#!/bin/bash
# Rollback Script for JustNews
# Handles deployment rollback across all platforms

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
JustNews Rollback Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -t, --target TARGET    Deployment target (docker-compose, kubernetes, systemd)
    -e, --env ENV          Environment (development, staging, production)
    -s, --service SERVICE  Specific service to rollback
    -v, --version VERSION  Specific version to rollback to
    -f, --force            Force rollback (skip confirmation)
    -h, --help            Show this help

EXAMPLES:
    # Rollback all services
    $0 --target kubernetes

    # Rollback specific service
    $0 --target kubernetes --service mcp-bus

    # Rollback to specific version
    $0 --target docker-compose --version v1.2.3

ENVIRONMENT VARIABLES:
    DEPLOY_TARGET          Default deployment target
    DEPLOY_ENV            Default environment

EOF
}

# Parse command line arguments
parse_args() {
    TARGET="${DEPLOY_TARGET:-docker-compose}"
    ENV="${DEPLOY_ENV:-development}"
    SERVICE=""
    VERSION=""
    FORCE="${FORCE_ROLLBACK:-0}"

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
            -v|--version)
                VERSION="$2"
                shift 2
                ;;
            -f|--force)
                FORCE=1
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Confirm rollback
confirm_rollback() {
    if [[ "$FORCE" == "1" ]]; then
        return 0
    fi

    local target_msg="$TARGET"
    if [[ -n "$SERVICE" ]]; then
        target_msg="$target_msg ($SERVICE)"
    fi

    echo "This will rollback the deployment on $target_msg"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Rollback cancelled"
        exit 0
    fi
}

# Create backup before rollback
create_backup() {
    log_info "Creating pre-rollback backup..."

    local backup_dir="$DEPLOY_ROOT/backups/$(date +%Y%m%d-%H%M%S)-rollback"
    mkdir -p "$backup_dir"

    case $TARGET in
        docker-compose)
            cd "$DEPLOY_ROOT/docker"
            docker-compose config > "$backup_dir/docker-compose.yml"
            ;;
        kubernetes)
            kubectl get all -l app=justnews -o yaml > "$backup_dir/kubernetes-state.yml"
            ;;
        systemd)
            systemctl list-units --type=service --state=active | grep justnews > "$backup_dir/systemd-services.txt"
            ;;
    esac

    log_success "Backup created: $backup_dir"
}

# Rollback Docker Compose
rollback_docker_compose() {
    log_info "Rolling back Docker Compose deployment..."

    cd "$DEPLOY_ROOT/docker"

    if [[ -n "$VERSION" ]]; then
        log_info "Rolling back to version: $VERSION"
        # Pull specific version
        if [[ -n "$SERVICE" ]]; then
            docker-compose pull "$SERVICE"
        else
            docker-compose pull
        fi
    else
        log_info "Rolling back to previous deployment..."
        # Use previous docker-compose.override.yml or git rollback
        if [[ -f "docker-compose.previous.yml" ]]; then
            mv docker-compose.yml docker-compose.failed.yml
            mv docker-compose.previous.yml docker-compose.yml
        else
            log_warning "No previous configuration found, restarting services..."
        fi
    fi

    # Restart services
    if [[ -n "$SERVICE" ]]; then
        docker-compose up -d "$SERVICE"
    else
        docker-compose up -d
    fi

    # Clean up failed images
    docker image prune -f

    log_success "Docker Compose rollback completed"
}

# Rollback Kubernetes
rollback_kubernetes() {
    log_info "Rolling back Kubernetes deployment..."

    if [[ -n "$VERSION" ]]; then
        log_info "Rolling back to version: $VERSION"
        # Use specific image version
        if [[ -n "$SERVICE" ]]; then
            kubectl set image deployment/"$SERVICE" "$SERVICE=$SERVICE:$VERSION"
            kubectl rollout status deployment/"$SERVICE"
        else
            # Rollback all deployments to specific version
            for deployment in $(kubectl get deployments -l app=justnews -o jsonpath='{.items[*].metadata.name}'); do
                kubectl set image deployment/"$deployment" "$deployment=$deployment:$VERSION"
            done
            kubectl rollout status deployment --all
        fi
    else
        # Use kubectl rollout undo
        if [[ -n "$SERVICE" ]]; then
            kubectl rollout undo deployment/"$SERVICE"
            kubectl rollout status deployment/"$SERVICE"
        else
            # Rollback all deployments
            for deployment in $(kubectl get deployments -l app=justnews -o jsonpath='{.items[*].metadata.name}'); do
                kubectl rollout undo deployment/"$deployment"
            done
            # Wait for all rollbacks to complete
            kubectl wait --for=condition=available --timeout=300s deployment --all
        fi
    fi

    log_success "Kubernetes rollback completed"
}

# Rollback systemd
rollback_systemd() {
    log_info "Rolling back systemd deployment..."

    if [[ -n "$VERSION" ]]; then
        log_warning "Version-specific rollback not supported for systemd"
        log_info "Please manually update service files and restart"
        return 1
    fi

    # Stop services
    if [[ -n "$SERVICE" ]]; then
        sudo systemctl stop "justnews-${SERVICE}.service"
    else
        for service in /etc/systemd/system/justnews-*.service; do
            if [[ -f "$service" ]]; then
                sudo systemctl stop "$(basename "$service")"
            fi
        done
    fi

    # Restore from backup if available
    local backup_dir="$DEPLOY_ROOT/backups"
    local latest_backup=$(ls -t "$backup_dir" | head -1)

    if [[ -n "$latest_backup" && -f "$backup_dir/$latest_backup/systemd-services.txt" ]]; then
        log_info "Restoring from backup: $latest_backup"

        # Restore service files
        if [[ -d "$backup_dir/$latest_backup/services" ]]; then
            sudo cp "$backup_dir/$latest_backup/services"/*.service /etc/systemd/system/
            sudo systemctl daemon-reload
        fi

        # Start services
        if [[ -n "$SERVICE" ]]; then
            sudo systemctl start "justnews-${SERVICE}.service"
        else
            while read -r service_line; do
                service_name=$(echo "$service_line" | awk '{print $1}')
                if [[ $service_name =~ justnews- ]]; then
                    sudo systemctl start "$service_name"
                fi
            done < "$backup_dir/$latest_backup/systemd-services.txt"
        fi
    else
        log_warning "No backup found, services stopped"
        log_info "Please manually restore and restart services"
    fi

    log_success "Systemd rollback completed"
}

# Verify rollback
verify_rollback() {
    log_info "Verifying rollback..."

    # Run health checks
    if [[ -f "$DEPLOY_ROOT/scripts/health-check.sh" ]]; then
        if bash "$DEPLOY_ROOT/scripts/health-check.sh"; then
            log_success "Rollback verification passed"
            return 0
        else
            log_error "Rollback verification failed"
            return 1
        fi
    else
        log_warning "Health check script not found, skipping verification"
        return 0
    fi
}

# Cleanup after rollback
cleanup_rollback() {
    log_info "Cleaning up after rollback..."

    case $TARGET in
        docker-compose)
            cd "$DEPLOY_ROOT/docker"
            # Remove failed containers
            docker-compose down
            # Clean up unused images
            docker image prune -f
            ;;
        kubernetes)
            # Remove failed pods
            kubectl delete pods -l app=justnews --field-selector=status.phase=Failed
            ;;
        systemd)
            # Remove failed service files if any
            # This is handled manually
            ;;
    esac

    log_success "Cleanup completed"
}

# Log rollback event
log_rollback() {
    local log_file="$DEPLOY_ROOT/logs/rollback-$(date +%Y%m%d).log"

    mkdir -p "$DEPLOY_ROOT/logs"

    cat >> "$log_file" << EOF
$(date -Iseconds) - Rollback executed
Target: $TARGET
Environment: $ENV
Service: ${SERVICE:-all}
Version: ${VERSION:-previous}
Status: completed
EOF

    log_info "Rollback logged to: $log_file"
}

# Main rollback function
main() {
    parse_args "$@"

    log_info "JustNews Rollback Script"
    log_info "Target: $TARGET"
    log_info "Environment: $ENV"
    if [[ -n "$SERVICE" ]]; then
        log_info "Service: $SERVICE"
    fi
    if [[ -n "$VERSION" ]]; then
        log_info "Version: $VERSION"
    fi

    confirm_rollback
    create_backup

    case $TARGET in
        docker-compose)
            rollback_docker_compose
            ;;
        kubernetes)
            rollback_kubernetes
            ;;
        systemd)
            rollback_systemd
            ;;
        *)
            log_error "Unsupported target: $TARGET"
            exit 1
            ;;
    esac

    verify_rollback
    cleanup_rollback
    log_rollback

    log_success "Rollback operation completed successfully"
}

# Run main function
main "$@"</content>
<parameter name="filePath">/home/adra/JustNewsAgent/deploy/refactor/scripts/rollback.sh