#!/bin/bash
## DEPRECATED: Original PostgreSQL setup script.
## The JustNews deployment now uses MariaDB (and Chroma for vector storage).
## This script provides a convenience MariaDB setup for local/systemd deployments.

set -euo pipefail

# Configuration - safe defaults for local/dev installs
JUSTNEWS_USER="justnews"
JUSTNEWS_PASSWORD="justnews_password"
MAIN_DB="justnews"
MEMORY_DB="justnews_memory"
MARIADB_PORT=3306

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (sudo)"
        exit 1
    fi
}

install_mariadb() {
    log_info "Installing MariaDB server and client packages..."
    apt update
    apt install -y mariadb-server mariadb-client
    log_success "MariaDB installed"
}

configure_mariadb() {
    log_info "Configuring MariaDB: enabling service and creating user/databases"
    systemctl enable mariadb
    systemctl start mariadb

    # Wait for MariaDB to start
    sleep 3

    # Create user and databases
    mysql -uroot <<EOF
CREATE DATABASE IF NOT EXISTS \\`${MAIN_DB}\\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS \\`${MEMORY_DB}\\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${JUSTNEWS_USER}'@'localhost' IDENTIFIED BY '${JUSTNEWS_PASSWORD}';
GRANT ALL PRIVILEGES ON \\`${MAIN_DB}\\`.* TO '${JUSTNEWS_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \\`${MEMORY_DB}\\`.* TO '${JUSTNEWS_USER}'@'localhost';
FLUSH PRIVILEGES;
EOF

    log_success "Databases and user created"
}

setup_monitoring() {
    log_info "Setting up backup script and log directory for MariaDB"
    mkdir -p /var/backups/mariadb
    chown mysql:mysql /var/backups/mariadb || true

    cat > /usr/local/bin/justnews-mariadb-backup.sh <<'EOF'
#!/bin/bash
# MariaDB backup script for JustNews
BACKUP_DIR="/var/backups/mariadb"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
MAIN_DB="justnews"
MEMORY_DB="justnews_memory"

mkdir -p "$BACKUP_DIR"
mysqldump -u justnews -p"justnews_password" "$MAIN_DB" > "$BACKUP_DIR/${MAIN_DB}_$TIMESTAMP.sql"
mysqldump -u justnews -p"justnews_password" "$MEMORY_DB" > "$BACKUP_DIR/${MEMORY_DB}_$TIMESTAMP.sql"
gzip "$BACKUP_DIR/${MAIN_DB}_$TIMESTAMP.sql"
gzip "$BACKUP_DIR/${MEMORY_DB}_$TIMESTAMP.sql"
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete
echo "MariaDB backup completed: $TIMESTAMP"
EOF

    chmod +x /usr/local/bin/justnews-mariadb-backup.sh

    cat > /etc/cron.daily/justnews-mariadb-backup <<'EOF'
#!/bin/bash
/usr/local/bin/justnews-mariadb-backup.sh >> /var/log/justnews/mariadb_backup.log 2>&1
EOF

    chmod +x /etc/cron.daily/justnews-mariadb-backup
    mkdir -p /var/log/justnews
    chown mysql:mysql /var/log/justnews || true

    log_success "Backup and monitoring hooks created"
}

test_databases() {
    log_info "Testing MariaDB connectivity using justnews user"
    if mysql -u"${JUSTNEWS_USER}" -p"${JUSTNEWS_PASSWORD}" -e "SELECT VERSION();" >/dev/null 2>&1; then
        log_success "MariaDB connection successful"
    else
        log_error "Failed to connect to MariaDB with the provided credentials"
        return 1
    fi
}

show_usage() {
    cat <<EOF
JustNews MariaDB Setup (replacement for legacy PostgreSQL script)

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help          Show this help message
    -u, --user USER     Database user to create (default: justnews)
    -p, --password PWD  Database password (default: justnews_password)
    --no-backup         Skip backup configuration

NOTES:
    - This script is intended for local or systemd-based deployments for convenience.
    - In production, you should provision MariaDB via your platform tooling and secrets manager.
    - The project uses Chroma (or external vector store) for embeddings; MariaDB stores relational data only.
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help) show_usage; exit 0 ;; 
            -u|--user) JUSTNEWS_USER="$2"; shift 2 ;; 
            -p|--password) JUSTNEWS_PASSWORD="$2"; shift 2 ;; 
            --no-backup) SKIP_BACKUP=true; shift ;; 
            *) log_error "Unknown option: $1"; show_usage; exit 1 ;; 
        esac
    done
}

main() {
    parse_args "$@"
    echo "========================================"
    log_info "JustNews MariaDB Setup (legacy PostgreSQL replacement)"
    echo "========================================"
    echo

    check_root

    install_mariadb
    configure_mariadb
    if [[ "${SKIP_BACKUP:-false}" != true ]]; then
        setup_monitoring
    else
        log_info "Skipping backup configuration"
    fi
    test_databases

    echo
    echo "Database URLs for JustNews environment files:"
    echo "Main DB:    mysql://${JUSTNEWS_USER}:${JUSTNEWS_PASSWORD}@localhost:${MARIADB_PORT}/${MAIN_DB}"
    echo "Memory DB:  mysql://${JUSTNEWS_USER}:${JUSTNEWS_PASSWORD}@localhost:${MARIADB_PORT}/${MEMORY_DB}"
    echo
    echo "IMPORTANT: This script replaces the original PostgreSQL helper."
    echo "If you're running in production, provision MariaDB via your platform tooling and update secrets accordingly."
}

main "$@"
