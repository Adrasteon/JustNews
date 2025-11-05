#!/bin/bash
# setup_postgresql.sh - PostgreSQL setup for JustNews systemd deployment
# Sets up native PostgreSQL databases for JustNews agents

set -euo pipefail

# Configuration
JUSTNEWS_USER="justnews"
JUSTNEWS_PASSWORD="justnews_password"
MAIN_DB="justnews"
MEMORY_DB="justnews_memory"
PG_VERSION="15"  # Ubuntu 22.04 default

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

# Install PostgreSQL
install_postgresql() {
    log_info "Installing PostgreSQL $PG_VERSION..."

    # Update package list
    apt update

    # Install PostgreSQL
    apt install -y postgresql-$PG_VERSION postgresql-contrib-$PG_VERSION

    # Install additional tools
    apt install -y postgresql-client-$PG_VERSION pgvector

    log_success "PostgreSQL installed successfully"
}

# Configure PostgreSQL
configure_postgresql() {
    log_info "Configuring PostgreSQL..."

    # Start PostgreSQL service
    systemctl enable postgresql
    systemctl start postgresql

    # Wait for PostgreSQL to start
    sleep 5

    # Create JustNews user and databases
    sudo -u postgres psql << EOF
-- Create JustNews user
CREATE USER $JUSTNEWS_USER WITH PASSWORD '$JUSTNEWS_PASSWORD';
ALTER USER $JUSTNEWS_USER CREATEDB;

-- Create main database
CREATE DATABASE $MAIN_DB OWNER $JUSTNEWS_USER;

-- Create memory database
CREATE DATABASE $MEMORY_DB OWNER $JUSTNEWS_USER;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE $MAIN_DB TO $JUSTNEWS_USER;
GRANT ALL PRIVILEGES ON DATABASE $MEMORY_DB TO $JUSTNEWS_USER;

-- Enable pgvector extension in memory database
\c $MEMORY_DB
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create analytics schema in main database
\c $MAIN_DB
CREATE SCHEMA IF NOT EXISTS analytics;
GRANT ALL ON SCHEMA analytics TO $JUSTNEWS_USER;
EOF

    log_success "PostgreSQL databases created and configured"
}

# Configure PostgreSQL for production
configure_production() {
    log_info "Configuring PostgreSQL for production..."

    # Backup original configuration
    cp /etc/postgresql/$PG_VERSION/main/postgresql.conf /etc/postgresql/$PG_VERSION/main/postgresql.conf.backup
    cp /etc/postgresql/$PG_VERSION/main/pg_hba.conf /etc/postgresql/$PG_VERSION/main/pg_hba.conf.backup

    # Configure postgresql.conf for JustNews
    cat >> /etc/postgresql/$PG_VERSION/main/postgresql.conf << EOF

# JustNews Production Configuration
# Memory settings (adjust based on system RAM)
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB

# Connection settings
max_connections = 100
tcp_keepalives_idle = 60
tcp_keepalives_interval = 10

# Logging
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
log_statement = 'ddl'
log_duration = on

# Performance
random_page_cost = 1.1
effective_io_concurrency = 200

# Extensions
shared_preload_libraries = 'pg_stat_statements'
EOF

    # Configure pg_hba.conf for local connections
    cat >> /etc/postgresql/$PG_VERSION/main/pg_hba.conf << EOF

# JustNews local connections
local   $MAIN_DB        $JUSTNEWS_USER                          md5
local   $MEMORY_DB      $JUSTNEWS_USER                          md5
host    $MAIN_DB        $JUSTNEWS_USER     127.0.0.1/32        md5
host    $MEMORY_DB      $JUSTNEWS_USER     127.0.0.1/32        md5
EOF

    # Restart PostgreSQL to apply changes
    systemctl restart postgresql

    log_success "PostgreSQL production configuration applied"
}

# Setup monitoring and backup
setup_monitoring() {
    log_info "Setting up monitoring and backup..."

    # Create backup directory
    mkdir -p /var/backups/postgresql
    chown postgres:postgres /var/backups/postgresql

    # Create backup script
    cat > /usr/local/bin/justnews-postgres-backup.sh << 'EOF'
#!/bin/bash
# PostgreSQL backup script for JustNews

BACKUP_DIR="/var/backups/postgresql"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
MAIN_DB="justnews"
MEMORY_DB="justnews_memory"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Backup main database
pg_dump -U justnews -h localhost "$MAIN_DB" > "$BACKUP_DIR/${MAIN_DB}_$TIMESTAMP.sql"

# Backup memory database
pg_dump -U justnews -h localhost "$MEMORY_DB" > "$BACKUP_DIR/${MEMORY_DB}_$TIMESTAMP.sql"

# Compress backups
gzip "$BACKUP_DIR/${MAIN_DB}_$TIMESTAMP.sql"
gzip "$BACKUP_DIR/${MEMORY_DB}_$TIMESTAMP.sql"

# Clean up old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "PostgreSQL backup completed: $TIMESTAMP"
EOF

    chmod +x /usr/local/bin/justnews-postgres-backup.sh

    # Setup daily backup cron job
    cat > /etc/cron.daily/justnews-postgres-backup << 'EOF'
#!/bin/bash
/usr/local/bin/justnews-postgres-backup.sh >> /var/log/justnews/postgres_backup.log 2>&1
EOF

    chmod +x /etc/cron.daily/justnews-postgres-backup

    # Create log directory
    mkdir -p /var/log/justnews
    chown postgres:postgres /var/log/justnews

    log_success "PostgreSQL monitoring and backup configured"
}

# Test database connectivity
test_databases() {
    log_info "Testing database connectivity..."

    # Test main database
    if PGPASSWORD="$JUSTNEWS_PASSWORD" psql -U "$JUSTNEWS_USER" -h localhost -d "$MAIN_DB" -c "SELECT version();" >/dev/null 2>&1; then
        log_success "Main database ($MAIN_DB) connection successful"
    else
        log_error "Failed to connect to main database"
        return 1
    fi

    # Test memory database
    if PGPASSWORD="$JUSTNEWS_PASSWORD" psql -U "$JUSTNEWS_USER" -h localhost -d "$MEMORY_DB" -c "SELECT version();" >/dev/null 2>&1; then
        log_success "Memory database ($MEMORY_DB) connection successful"
    else
        log_error "Failed to connect to memory database"
        return 1
    fi

    # Test pgvector extension
    if PGPASSWORD="$JUSTNEWS_PASSWORD" psql -U "$JUSTNEWS_USER" -h localhost -d "$MEMORY_DB" -c "SELECT * FROM pg_extension WHERE extname = 'vector';" | grep -q vector; then
        log_success "pgvector extension available"
    else
        log_warning "pgvector extension not found (optional)"
    fi

    log_success "Database connectivity tests passed"
}

# Show usage
show_usage() {
    cat << EOF
JustNews PostgreSQL Setup Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help          Show this help message
    -v, --version VER   PostgreSQL version to install (default: 15)
    -u, --user USER     Database user to create (default: justnews)
    -p, --password PWD  Database password (default: justnews_password)
    --no-backup         Skip backup configuration
    --no-production     Skip production configuration

DESCRIPTION:
    Sets up native PostgreSQL databases for JustNews systemd deployment.
    Creates two databases: justnews (main) and justnews_memory (vector storage).

DATABASES CREATED:
    - justnews: Main application database
    - justnews_memory: Vector embeddings and semantic search

EXTENSIONS INSTALLED:
    - pgvector: Vector similarity search
    - pg_trgm: Text similarity search
    - pg_stat_statements: Query performance monitoring

EXAMPLES:
    $0                          # Full setup with defaults
    $0 --version 14             # Install PostgreSQL 14
    $0 --no-backup              # Skip backup configuration

NOTES:
    - Requires root privileges
    - Configures PostgreSQL for production use
    - Sets up automated daily backups
    - Enables monitoring and performance tuning
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -v|--version)
                PG_VERSION="$2"
                shift 2
                ;;
            -u|--user)
                JUSTNEWS_USER="$2"
                shift 2
                ;;
            -p|--password)
                JUSTNEWS_PASSWORD="$2"
                shift 2
                ;;
            --no-backup)
                SKIP_BACKUP=true
                shift
                ;;
            --no-production)
                SKIP_PRODUCTION=true
                shift
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
    parse_args "$@"

    echo "========================================"
    log_info "JustNews PostgreSQL Setup"
    echo "========================================"
    echo

    check_root

    local steps=(
        "install_postgresql"
        "configure_postgresql"
        "configure_production"
        "setup_monitoring"
        "test_databases"
    )

    for step in "${steps[@]}"; do
        echo
        if $step; then
            log_success "✓ $step completed"
        else
            log_error "✗ $step failed"
            exit 1
        fi
    done

    echo
    echo "========================================"
    log_success "PostgreSQL setup completed successfully!"
    echo "========================================"
    echo
    echo "Database URLs for JustNews environment files:"
    echo "Main DB:    postgresql://$JUSTNEWS_USER:$JUSTNEWS_PASSWORD@localhost:5432/$MAIN_DB"
    echo "Memory DB:  postgresql://$JUSTNEWS_USER:$JUSTNEWS_PASSWORD@localhost:5432/$MEMORY_DB"
    echo
    echo "Next steps:"
    echo "1. Update /etc/justnews/global.env with database URLs"
    echo "2. Update /etc/justnews/memory.env with database URLs"
    echo "3. Run JustNews preflight check: ./infrastructure/systemd/preflight.sh"
    echo "4. Start services: sudo ./infrastructure/systemd/scripts/enable_all.sh start"
}

# Run main function
main "$@"
