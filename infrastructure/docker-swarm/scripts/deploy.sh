#!/bin/bash

# JustNews Docker Swarm Deployment Script
# This script manages the complete Docker Swarm deployment lifecycle

set -e

COMPOSE_FILE="docker-compose.swarm.yml"
STACK_NAME="justnews"
SWARM_ADVERTISE_ADDR="${SWARM_ADVERTISE_ADDR:-eth0}"

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

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running or you don't have permissions"
        exit 1
    fi

    log_success "Docker is available"
}

# Check if Swarm is initialized
check_swarm() {
    if ! docker info --format '{{.Swarm.LocalNodeState}}' | grep -q "active"; then
        log_warning "Docker Swarm is not initialized"
        return 1
    fi

    log_success "Docker Swarm is active"
    return 0
}

# Initialize Swarm
init_swarm() {
    log_info "Initializing Docker Swarm..."

    if ! docker swarm init --advertise-addr "$SWARM_ADVERTISE_ADDR" 2>/dev/null; then
        log_error "Failed to initialize Swarm. It might already be initialized or you need to specify a different advertise address."
        log_info "Try: export SWARM_ADVERTISE_ADDR=your_ip_address"
        exit 1
    fi

    log_success "Docker Swarm initialized"
}

# Label nodes for GPU support
label_gpu_nodes() {
    log_info "Labeling GPU nodes..."

    # Check if this node is a manager
    if ! docker node ls &>/dev/null; then
        log_warning "Not a Swarm manager node. Skipping GPU node labeling."
        return
    fi

    # Get all nodes
    NODES=$(docker node ls --format "{{.ID}}" 2>/dev/null || echo "")

    if [ -z "$NODES" ]; then
        log_warning "No nodes found. Skipping GPU node labeling."
        return
    fi

    for NODE in $NODES; do
        # Check if node has GPU capabilities
        if docker node inspect "$NODE" --format '{{.Description.Platform.Architecture}}' 2>/dev/null | grep -q "x86_64\|amd64"; then
            # Try to detect NVIDIA GPU
            if docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi &>/dev/null; then
                docker node update --label-add gpu=true "$NODE"
                log_success "Labeled node $NODE as GPU-enabled"
            else
                docker node update --label-add gpu=false "$NODE"
                log_info "Labeled node $NODE as CPU-only"
            fi
        fi
    done
}

# Create secrets
create_secrets() {
    log_info "Creating Docker secrets..."

    # Check if this node is a manager
    if ! docker node ls &>/dev/null; then
        log_warning "Not a Swarm manager node. Skipping secret creation."
        log_info "Please run this command on a Swarm manager node."
        return
    fi

    # Check if secrets already exist
    if docker secret ls --format "{{.Name}}" | grep -q "^postgres_password$"; then
        log_warning "Secrets already exist. Skipping creation."
        return
    fi

    # Create secrets from environment variables or defaults
    echo "${POSTGRES_PASSWORD:-change_me_secure_postgres_password}" | docker secret create postgres_password -
    echo "${REDIS_PASSWORD:-change_me_secure_redis_password}" | docker secret create redis_password -
    echo "${GRAFANA_ADMIN_USER:-admin}" | docker secret create grafana_admin_user -
    echo "${GRAFANA_ADMIN_PASSWORD:-change_me_secure_grafana_password}" | docker secret create grafana_admin_password -

    log_success "Docker secrets created"
}

# Deploy stack
deploy_stack() {
    log_info "Deploying JustNews stack..."

    docker stack deploy -c "$COMPOSE_FILE" "$STACK_NAME"

    log_success "JustNews stack deployed"
}

# Check deployment status
check_deployment() {
    log_info "Checking deployment status..."

    # Wait for services to be created
    sleep 10

    # Check service status
    SERVICES=$(docker stack services "$STACK_NAME" --format "{{.Name}} {{.Replicas}}")

    echo "$SERVICES" | while read -r SERVICE REPLICAS; do
        SERVICE_NAME=$(basename "$SERVICE")
        if echo "$REPLICAS" | grep -q "/"; then
            CURRENT=$(echo "$REPLICAS" | cut -d'/' -f1)
            DESIRED=$(echo "$REPLICAS" | cut -d'/' -f2)
            if [ "$CURRENT" -eq "$DESIRED" ]; then
                log_success "Service $SERVICE_NAME: $REPLICAS (Ready)"
            else
                log_warning "Service $SERVICE_NAME: $REPLICAS (Starting...)"
            fi
        else
            log_info "Service $SERVICE_NAME: $REPLICAS"
        fi
    done
}

# Remove stack
remove_stack() {
    log_info "Removing JustNews stack..."

    docker stack rm "$STACK_NAME"

    # Wait for removal
    sleep 5

    log_success "JustNews stack removed"
}

# Backup data
backup_data() {
    log_info "Creating backup of JustNews data..."

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="./backups/$TIMESTAMP"

    mkdir -p "$BACKUP_DIR"

    # Backup PostgreSQL
    log_info "Backing up PostgreSQL database..."
    docker exec $(docker ps -q -f name=justnews_postgres) pg_dump -U justnews justnews > "$BACKUP_DIR/postgres_backup.sql"

    # Backup Redis (if using persistence)
    log_info "Backing up Redis data..."
    docker run --rm -v justnews_redis_data:/data -v $(pwd)/$BACKUP_DIR:/backup alpine tar czf /backup/redis_backup.tar.gz -C /data .

    # Backup Grafana data
    log_info "Backing up Grafana data..."
    docker run --rm -v justnews_grafana_data:/data -v $(pwd)/$BACKUP_DIR:/backup alpine tar czf /backup/grafana_backup.tar.gz -C /data .

    # Backup configurations
    cp docker-compose.swarm.yml "$BACKUP_DIR/"
    cp .env.swarm "$BACKUP_DIR/" 2>/dev/null || true

    log_success "Backup completed: $BACKUP_DIR"
}

# Restore data
restore_data() {
    if [ -z "$2" ]; then
        log_error "Usage: $0 restore BACKUP_DIR"
        exit 1
    fi

    BACKUP_DIR="$2"

    if [ ! -d "$BACKUP_DIR" ]; then
        log_error "Backup directory does not exist: $BACKUP_DIR"
        exit 1
    fi

    log_info "Restoring data from $BACKUP_DIR..."

    # Stop services before restore
    log_info "Stopping services for restore..."
    docker stack rm "$STACK_NAME"
    sleep 30

    # Restore PostgreSQL
    if [ -f "$BACKUP_DIR/postgres_backup.sql" ]; then
        log_info "Restoring PostgreSQL database..."
        docker run --rm -v justnews_postgres_data:/var/lib/postgresql/data -v $BACKUP_DIR:/backup postgres:15-alpine sh -c "psql -h postgres -U justnews -d justnews < /backup/postgres_backup.sql"
    fi

    # Restore Redis
    if [ -f "$BACKUP_DIR/redis_backup.tar.gz" ]; then
        log_info "Restoring Redis data..."
        docker run --rm -v justnews_redis_data:/data -v $BACKUP_DIR:/backup alpine sh -c "cd /data && tar xzf /backup/redis_backup.tar.gz"
    fi

    # Restore Grafana
    if [ -f "$BACKUP_DIR/grafana_backup.tar.gz" ]; then
        log_info "Restoring Grafana data..."
        docker run --rm -v justnews_grafana_data:/data -v $BACKUP_DIR:/backup alpine sh -c "cd /data && tar xzf /backup/grafana_backup.tar.gz"
    fi

    # Restart services
    log_info "Restarting services..."
    deploy_stack
    check_deployment

    log_success "Data restoration completed"
}

# Show usage
usage() {
    cat << EOF
JustNews Docker Swarm Deployment Script

Usage: $0 [COMMAND]

Commands:
    init        Initialize Swarm and create secrets
    deploy      Deploy the JustNews stack
    status      Check deployment status
    remove      Remove the JustNews stack
    logs        Show logs for all services
    scale       Scale a service (usage: scale SERVICE=REPLICAS)
    update      Update the stack with new images
    backup      Create backup of all data
    restore     Restore data from backup (usage: restore BACKUP_DIR)
    cleanup     Remove unused Docker objects

Environment Variables:
    SWARM_ADVERTISE_ADDR    Advertise address for Swarm (default: eth0)
    POSTGRES_PASSWORD       PostgreSQL password
    REDIS_PASSWORD          Redis password
    GRAFANA_ADMIN_USER      Grafana admin username
    GRAFANA_ADMIN_PASSWORD  Grafana admin password

Examples:
    $0 init
    $0 deploy
    $0 scale justnews_scout=3
    $0 logs
    $0 status
    $0 backup
    $0 restore ./backups/20230101_120000

EOF
}

# Main command handling
case "${1:-help}" in
    init)
        check_docker
        if ! check_swarm; then
            init_swarm
        fi
        label_gpu_nodes
        create_secrets
        ;;
    deploy)
        check_docker
        check_swarm
        deploy_stack
        check_deployment
        ;;
    status)
        check_docker
        check_swarm
        check_deployment
        ;;
    remove)
        check_docker
        remove_stack
        ;;
    logs)
        check_docker
        docker stack services "$STACK_NAME" --format "{{.Name}}" | xargs -I {} docker service logs {}
        ;;
    scale)
        if [ -z "$2" ]; then
            log_error "Usage: $0 scale SERVICE=REPLICAS"
            exit 1
        fi
        check_docker
        check_swarm
        docker service scale "$2"
        ;;
    update)
        check_docker
        check_swarm
        log_info "Updating stack with new images..."
        docker stack deploy -c "$COMPOSE_FILE" "$STACK_NAME"
        ;;
    backup)
        check_docker
        check_swarm
        backup_data
        ;;
    restore)
        if [ -z "$2" ]; then
            log_error "Usage: $0 restore BACKUP_DIR"
            exit 1
        fi
        check_docker
        restore_data "$@"
        ;;
    cleanup)
        check_docker
        log_info "Cleaning up unused Docker objects..."
        docker system prune -f
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