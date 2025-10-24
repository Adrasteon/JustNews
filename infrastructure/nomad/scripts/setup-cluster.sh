#!/bin/bash

# JustNews Nomad Cluster Setup Script
# This script helps set up a basic Nomad cluster for development/testing

set -e

# Configuration
SERVER_COUNT="${SERVER_COUNT:-1}"
CLIENT_COUNT="${CLIENT_COUNT:-1}"
INSTALL_DIR="${INSTALL_DIR:-/opt/nomad-setup}"

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

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root (sudo $0)"
        exit 1
    fi
}

# Install dependencies
install_dependencies() {
    log_info "Installing dependencies..."

    # Update package list
    apt update

    # Install required packages
    apt install -y curl wget jq unzip

    log_success "Dependencies installed"
}

# Install Docker
install_docker() {
    log_info "Installing Docker..."

    if command -v docker &> /dev/null; then
        log_info "Docker already installed"
        return
    fi

    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker

    log_success "Docker installed"
}

# Install Nomad
install_nomad() {
    log_info "Installing Nomad..."

    if command -v nomad &> /dev/null; then
        log_info "Nomad already installed"
        return
    fi

    wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/hashicorp.list
    apt update && apt install -y nomad

    log_success "Nomad installed"
}

# Install Consul
install_consul() {
    log_info "Installing Consul..."

    if command -v consul &> /dev/null; then
        log_info "Consul already installed"
        return
    fi

    wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/hashicorp.list
    apt update && apt install -y consul

    log_success "Consul installed"
}

# Setup directories
setup_directories() {
    log_info "Setting up directories..."

    mkdir -p /opt/nomad/data
    mkdir -p /opt/consul/data
    mkdir -p /etc/nomad.d
    mkdir -p /etc/consul.d

    # Set permissions
    chown -R nomad:nomad /opt/nomad
    chown -R consul:consul /opt/consul

    log_success "Directories configured"
}

# Configure Nomad server
configure_nomad_server() {
    log_info "Configuring Nomad server..."

    cat > /etc/nomad.d/nomad.hcl << EOF
datacenter = "dc1"
data_dir = "/opt/nomad/data"
bind_addr = "0.0.0.0"

server {
  enabled = true
  bootstrap_expect = $SERVER_COUNT
}

client {
  enabled = true
}

consul {
  address = "127.0.0.1:8500"
}

plugin "docker" {
  config {
    allow_privileged = true
  }
}

telemetry {
  prometheus_metrics = true
}
EOF

    log_success "Nomad server configured"
}

# Configure Consul server
configure_consul_server() {
    log_info "Configuring Consul server..."

    cat > /etc/consul.d/consul.hcl << EOF
datacenter = "dc1"
data_dir = "/opt/consul/data"
bind_addr = "0.0.0.0"
client_addr = "0.0.0.0"

server = true
bootstrap_expect = $SERVER_COUNT

ui_config {
  enabled = true
}

telemetry {
  prometheus_retention_time = "24h"
}
EOF

    log_success "Consul server configured"
}

# Start services
start_services() {
    log_info "Starting services..."

    systemctl enable nomad consul docker
    systemctl start nomad consul docker

    # Wait for services to start
    sleep 10

    log_success "Services started"
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."

    # Check Nomad
    if nomad server members &> /dev/null; then
        log_success "Nomad is running"
    else
        log_error "Nomad failed to start"
    fi

    # Check Consul
    if consul members &> /dev/null; then
        log_success "Consul is running"
    else
        log_error "Consul failed to start"
    fi

    # Check Docker
    if docker info &> /dev/null; then
        log_success "Docker is running"
    else
        log_error "Docker failed to start"
    fi
}

# Show usage
usage() {
    cat << EOF
JustNews Nomad Cluster Setup Script

This script sets up a basic Nomad cluster for development/testing.
Run this on each node in your cluster.

Usage: sudo $0 [OPTIONS]

Options:
    -s, --servers COUNT    Number of server nodes (default: 1)
    -c, --clients COUNT    Number of client nodes (default: 1)
    -h, --help            Show this help

Environment Variables:
    SERVER_COUNT          Number of server nodes
    CLIENT_COUNT          Number of client nodes
    INSTALL_DIR           Installation directory

Examples:
    sudo $0                          # Single node setup
    sudo $0 -s 3 -c 2               # 3 servers, 2 clients
    SERVER_COUNT=3 CLIENT_COUNT=2 sudo $0

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--servers)
            SERVER_COUNT="$2"
            shift 2
            ;;
        -c|--clients)
            CLIENT_COUNT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Main setup
main() {
    log_info "Starting JustNews Nomad cluster setup..."
    log_info "Servers: $SERVER_COUNT, Clients: $CLIENT_COUNT"

    check_root
    install_dependencies
    install_docker
    install_nomad
    install_consul
    setup_directories
    configure_nomad_server
    configure_consul_server
    start_services
    verify_installation

    log_success "Setup complete!"
    echo
    log_info "Next steps:"
    echo "1. Copy this script to other nodes and run it there"
    echo "2. Update server addresses in configuration files"
    echo "3. Run: cd infrastructure/nomad && ./scripts/deploy.sh deploy"
    echo
    log_info "Access points:"
    echo "  Nomad UI: http://localhost:4646"
    echo "  Consul UI: http://localhost:8500"
}

main "$@"