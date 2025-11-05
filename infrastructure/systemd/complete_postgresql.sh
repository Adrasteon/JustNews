#!/bin/bash
# JustNews PostgreSQL Completion Script
# Completes the existing PostgreSQL setup by adding missing components

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_SRC_DIR="$SCRIPT_DIR/examples"

echo "🚀 JustNews PostgreSQL Completion Script"
echo "========================================"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should NOT be run as root. Please run as a regular user with sudo access."
   exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}📋 Checking current PostgreSQL status...${NC}"

# Check if PostgreSQL is running
if ! systemctl is-active --quiet postgresql; then
    echo -e "${RED}❌ PostgreSQL service is not running${NC}"
    echo "Starting PostgreSQL..."
    sudo systemctl start postgresql
    sudo systemctl enable postgresql
fi

echo -e "${GREEN}✅ PostgreSQL is running${NC}"

# Check existing databases
echo -e "${BLUE}📊 Checking existing databases...${NC}"
EXISTING_DBS=$(sudo -u postgres psql -c "SELECT datname FROM pg_database WHERE datname LIKE 'justnews%';" -t | tr -d ' ')

if echo "$EXISTING_DBS" | grep -q "^justnews$"; then
    echo -e "${GREEN}✅ justnews database exists${NC}"
else
    echo -e "${RED}❌ justnews database missing${NC}"
    exit 1
fi

if echo "$EXISTING_DBS" | grep -q "^justnews_memory$"; then
    echo -e "${GREEN}✅ justnews_memory database exists${NC}"
    echo -e "${YELLOW}⚠️  justnews_memory already exists - skipping creation${NC}"
    SKIP_MEMORY_DB=true
else
    echo -e "${YELLOW}📝 justnews_memory database needs to be created${NC}"
    SKIP_MEMORY_DB=false
fi

# Check if pgvector is installed
echo -e "${BLUE}🔧 Checking pgvector extension...${NC}"
if ! dpkg -l | grep -q postgresql-16-pgvector; then
    echo "Installing pgvector extension..."
    sudo apt update
    sudo apt install -y postgresql-16-pgvector
    echo -e "${GREEN}✅ pgvector installed${NC}"
else
    echo -e "${GREEN}✅ pgvector already installed${NC}"
fi

# Create justnews_memory database if it doesn't exist
if [[ "$SKIP_MEMORY_DB" == "false" ]]; then
    echo -e "${BLUE}🏗️  Creating justnews_memory database...${NC}"

    sudo -u postgres psql << EOF
-- Create justnews_memory database
CREATE DATABASE justnews_memory OWNER justnews_user;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE justnews_memory TO justnews_user;

-- Connect to justnews_memory and set up extensions
\c justnews_memory

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Grant usage on extensions to justnews_user
GRANT USAGE ON SCHEMA public TO justnews_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO justnews_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO justnews_user;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO justnews_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO justnews_user;
EOF

    echo -e "${GREEN}✅ justnews_memory database created and configured${NC}"
fi

# Verify database access
echo -e "${BLUE}🔍 Verifying database access...${NC}"

# Test justnews database
if PGPASSWORD=password123 psql -U justnews_user -h localhost -d justnews -c "SELECT 1;" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ justnews database accessible${NC}"
else
    echo -e "${RED}❌ Cannot access justnews database${NC}"
    exit 1
fi

# Test justnews_memory database
if PGPASSWORD=password123 psql -U justnews_user -h localhost -d justnews_memory -c "SELECT 1;" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ justnews_memory database accessible${NC}"
else
    echo -e "${RED}❌ Cannot access justnews_memory database${NC}"
    exit 1
fi

# Verify pgvector extension
VECTOR_COUNT=$(PGPASSWORD=password123 psql -U justnews_user -h localhost -d justnews_memory -c "SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector';" -t | tr -d ' ')
if [[ "$VECTOR_COUNT" -gt 0 ]]; then
    echo -e "${GREEN}✅ pgvector extension enabled${NC}"
else
    echo -e "${RED}❌ pgvector extension not enabled${NC}"
    exit 1
fi

# Update environment files
echo -e "${BLUE}📝 Updating environment files...${NC}"

# Copy updated environment files to /etc/justnews/
sudo mkdir -p /etc/justnews
shopt -s nullglob
for src in "$ENV_SRC_DIR"/*.env "$ENV_SRC_DIR"/*.env.example; do
    base="$(basename "$src")"
    if [[ "$base" == *.env.example ]]; then
        dest_name="${base%.env.example}.env"
    else
        dest_name="$base"
    fi
    sudo cp "$src" "/etc/justnews/$dest_name"
done
shopt -u nullglob

echo -e "${GREEN}✅ Environment files updated${NC}"

# Create database backup script
echo -e "${BLUE}💾 Setting up backup configuration...${NC}"

sudo mkdir -p /var/backups/postgresql
sudo chown postgres:postgres /var/backups/postgresql

# Create backup script
sudo tee /usr/local/bin/justnews-postgres-backup.sh > /dev/null << 'EOF'
#!/bin/bash
# JustNews PostgreSQL Backup Script

BACKUP_DIR="/var/backups/postgresql"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "📦 Creating PostgreSQL backups..."

# Backup justnews database
sudo -u postgres pg_dump justnews > "$BACKUP_DIR/justnews_$TIMESTAMP.sql"
gzip "$BACKUP_DIR/justnews_$TIMESTAMP.sql"

# Backup justnews_memory database
sudo -u postgres pg_dump justnews_memory > "$BACKUP_DIR/justnews_memory_$TIMESTAMP.sql"
gzip "$BACKUP_DIR/justnews_memory_$TIMESTAMP.sql"

echo "✅ Backups created:"
echo "   $BACKUP_DIR/justnews_$TIMESTAMP.sql.gz"
echo "   $BACKUP_DIR/justnews_memory_$TIMESTAMP.sql.gz"

# Clean up old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "🧹 Old backups cleaned up"
EOF

sudo chmod +x /usr/local/bin/justnews-postgres-backup.sh

# Setup daily backup cron job
if ! sudo crontab -l | grep -q justnews-postgres-backup; then
    echo "Setting up daily backup cron job..."
    (sudo crontab -l ; echo "0 2 * * * /usr/local/bin/justnews-postgres-backup.sh") | sudo crontab -
    echo -e "${GREEN}✅ Daily backup cron job configured${NC}"
else
    echo -e "${GREEN}✅ Daily backup cron job already exists${NC}"
fi

# Final verification
echo -e "${BLUE}🎯 Final verification...${NC}"

echo "Database Status:"
echo "  justnews: $(PGPASSWORD=password123 psql -U justnews_user -h localhost -d justnews -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" -t | tr -d ' ') tables"
echo "  justnews_memory: $(PGPASSWORD=password123 psql -U justnews_user -h localhost -d justnews_memory -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" -t | tr -d ' ') tables"

echo ""
echo -e "${GREEN}🎉 PostgreSQL completion successful!${NC}"
echo ""
echo "Summary of changes:"
echo "  ✅ Verified existing justnews database"
if [[ "$SKIP_MEMORY_DB" == "false" ]]; then
    echo "  ✅ Created justnews_memory database"
    echo "  ✅ Enabled pgvector extension"
fi
echo "  ✅ Updated environment files with correct credentials"
echo "  ✅ Configured automated backups"
echo "  ✅ Verified database access"
echo ""
echo "Environment files location: /etc/justnews/"
echo "Backup location: /var/backups/postgresql/"
echo "Backup script: /usr/local/bin/justnews-postgres-backup.sh"
echo ""
echo "Next steps:"
echo "  1. Enable systemd services: sudo ./infrastructure/systemd/scripts/enable_all.sh enable"
echo "  2. Start all services: sudo ./infrastructure/systemd/scripts/enable_all.sh start"
echo "  3. Health check: sudo ./infrastructure/systemd/scripts/health_check.sh"
