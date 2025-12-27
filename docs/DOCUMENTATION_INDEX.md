--- title: JustNews Documentation Index description: Complete guide to all JustNews documentation ---

# JustNews Documentation Index

This is a comprehensive index of all JustNews documentation, organized by topic and audience.

## 🚀 For New Operators (Start Here!)

**Essential Reading** (in order):

1. [Setup Guide](./operations/SETUP_GUIDE.md) — Complete installation from scratch

  - Python 3.12 and Miniconda setup

  - Conda environment creation

  - Global environment configuration

  - Vault OSS installation and initialization

  - MariaDB database setup

  - ChromaDB vector database setup

  - Verification and testing

  - Systemd integration

1. [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — Understanding and managing configuration

  - Global.env file structure

  - Secrets management integration

  - Environment variable reference

  - Troubleshooting common config issues

1. [Vault Administration](./operations/VAULT_SETUP.md) — Managing secrets securely

  - Vault architecture and design

  - AppRole authentication setup

  - Secret creation and rotation

  - Emergency procedures

  - Integration with systemd services

1. [Troubleshooting](./operations/TROUBLESHOOTING.md) — When things go wrong

  - Service health checks

  - Common issues and fixes

  - Emergency recovery procedures

  - Performance monitoring

1. [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) — Setting up Prometheus and Grafana

  - Pre-configured dashboards and configuration

  - Integration with service monitoring

  - Dashboard usage guide

1. **[Monitoring Quick Deploy](./operations/MONITORING_QUICK_DEPLOY.md)** — **⭐ Start here for quick deployment**

  - One-command deployment script

  - Full automation of installation and setup

  - Step-by-step guide for deployment

  - Troubleshooting tips

## 📋 For Operations / System Administrators

**Core Documentation**:

- [Setup Guide](./operations/SETUP_GUIDE.md) — End-to-end installation

- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — Config management

- [Vault Setup & Administration](./operations/VAULT_SETUP.md) — Secrets management

- [Troubleshooting](./operations/TROUBLESHOOTING.md) — Diagnostics and recovery

- [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) — Prometheus/Grafana deployment

**Deployment & Infrastructure**:

- [Systemd Operations](./infrastructure/systemd/README.md) — Service management

- [Operations Guide](./operations/README.md) — General operational procedures

**Monitoring & Maintenance**:

- [GPU Monitoring](./operations/gpu-monitoring.md) — GPU resource monitoring

- [Systemd Monitoring](./operations/systemd-monitoring.md) — Service health monitoring

- [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) — Prometheus and Grafana setup

- [Dashboard Quick Reference](./operations/dashboard-quick-reference.md) — Analytics dashboard

**Database Management**:

- [Database Documentation](../database/README.md) — MariaDB schema and migrations

- [Database ORM Guide](../database/core/) — ORM and connection pooling

## 👨‍💻 For Developers

**Setup for Development**:

1. Read [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) to understand the environment

1. Follow [Setup Guide Phase 1-2](./operations/SETUP_GUIDE.md#phase-1-python-312--miniconda) to set up your machine

1. Check out [Development Guide](./developer/) for coding standards

**Common Development Tasks**:

- [Testing Guide](./developer/) — Running tests locally

- [API Documentation](./api/) — REST API reference

- [Architecture Documentation](../docs/) — System design and patterns

**Environment & Configuration**:

- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — How to use environment variables

- [Global.env Reference](./operations/ENVIRONMENT_CONFIG.md#the-etcjustnewsglobalenv-file) — Configuration file structure

## 🔒 For Security / Compliance Teams

**Secrets & Authentication**:

- [Vault Setup & Administration](./operations/VAULT_SETUP.md) — Secrets management architecture

  - Vault OSS (open-source, no cloud dependency)

  - AppRole authentication

  - Secret rotation procedures

  - Emergency access procedures

**Security Considerations**:

- [Vault Setup - Security Section](./operations/VAULT_SETUP.md#security-considerations) — Best practices

- [Environment Configuration - Secrets](./operations/ENVIRONMENT_CONFIG.md#secrets-management) — Secrets hierarchy

## 📊 For Data / Analytics Teams

**Database Schema**:

- [Database Models](../database/models/) — Table definitions

- [Database README](../database/README.md) — Schema overview

**Analytics & Metrics**:

- [Dashboard Quick Reference](./operations/dashboard-quick-reference.md) — Analytics dashboard usage

- [Monitoring Guide](./operations/systemd-monitoring.md) — Metrics and monitoring

## 🎯 Topic-Based Index

### Installation & Setup

- [Setup Guide](./operations/SETUP_GUIDE.md) — Complete installation

- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — Configuration files

- [Vault Setup](./operations/VAULT_SETUP.md) — Secrets infrastructure

### Configuration Management

- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — Full guide

- [Global.env Reference](./operations/ENVIRONMENT_CONFIG.md#the-etcjustnewsglobalenv-file) — Configuration file

- [Environment Variables](./operations/ENVIRONMENT_CONFIG.md#common-environment-variables) — Variable reference

### Database Management

- [Database README](../database/README.md) — Overview

- [Database Models](../database/models/) — Table definitions

- [Database Migrations](../database/migrations/) — Schema versions

### Secrets & Security

- [Vault Setup & Administration](./operations/VAULT_SETUP.md) — Complete guide

- [AppRole Authentication](./operations/VAULT_SETUP.md#approle-authentication) — Service auth

- [Secret Rotation](./operations/VAULT_SETUP.md#secret-rotation) — Regular key rotation

- [Environment Secrets](./operations/ENVIRONMENT_CONFIG.md#secrets-management) — Using secrets in code

### Service Management

- [Setup Guide - Systemd Integration](./operations/SETUP_GUIDE.md#phase-7-systemd-integration-and-startup) — Service setup

- [Systemd Operations](./infrastructure/systemd/README.md) — Service commands

- [Systemd Monitoring](./operations/systemd-monitoring.md) — Health checks

### Monitoring & Troubleshooting

- [Troubleshooting Guide](./operations/TROUBLESHOOTING.md) — Complete reference

- [GPU Monitoring](./operations/gpu-monitoring.md) — GPU resources

- [Systemd Monitoring](./operations/systemd-monitoring.md) — Service health

- [Dashboard Reference](./operations/dashboard-quick-reference.md) — Analytics

### Deployment

- [Setup Guide](./operations/SETUP_GUIDE.md) — Initial deployment

- [Systemd Operations](./infrastructure/systemd/README.md) — Service deployment

- [Operations Guide](./operations/README.md) — General procedures

## 📁 Documentation File Locations

```

docs/
├── api/                           # REST API reference
├── developer/                     # Developer guides
├── operations/                    # Operational procedures
│   ├── SETUP_GUIDE.md            # ⭐ Start here: Complete installation
│   ├── ENVIRONMENT_CONFIG.md     # Configuration management
│   ├── VAULT_SETUP.md            # Secrets administration
│   ├── TROUBLESHOOTING.md        # Diagnostics & recovery
│   ├── README.md                 # Operations overview
│   ├── gpu-monitoring.md         # GPU monitoring
│   ├── systemd-monitoring.md     # Service health monitoring
│   └── ...
├── user-guides/                  # End-user documentation
├── CONTRIBUTING.md               # Contribution guidelines
└── ...

database/
├── README.md                      # Database architecture
├── models/                        # Table definitions
├── migrations/                    # Schema migrations
└── core/                          # ORM and utilities

infrastructure/
├── systemd/
│   └── README.md                 # Service management
└── ...

```

## 🔍 Quick Reference by Task

### "I'm new to JustNews and need to set up a machine"

→ Read [Setup Guide](./operations/SETUP_GUIDE.md) in order (7 phases)

### "I need to understand the configuration system"

→ Read [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md)

### "How do I manage secrets?"

→ Read [Vault Setup & Administration](./operations/VAULT_SETUP.md)

### "Something broke, how do I fix it?"

→ Read [Troubleshooting](./operations/TROUBLESHOOTING.md)

### "How do I monitor system and service health?"

→ Read [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md)

### "How do I run a test locally?"

→ Activate conda environment, then see [Development Guide](./developer/)

### "How do I deploy to production?"

→ Follow [Setup Guide](./operations/SETUP_GUIDE.md), then [Systemd Operations](./infrastructure/systemd/README.md)

### "Where is the database schema?"

→ See [Database README](../database/README.md) and [Models](../database/models/)

### "How do I rotate secrets?"

→ See [Vault Setup - Secret Rotation](./operations/VAULT_SETUP.md#secret- rotation)

### "How do I monitor system health?"

→ See [Troubleshooting - Monitoring](./operations/TROUBLESHOOTING.md#monitoring- and-observability)

### "What are all the environment variables?"

→ See [Environment Configuration - Common Variables](./operations/ENVIRONMENT_CONFIG.md#common-environment-variables)

## 📞 Getting Help

1. **Check the docs first**:

  - [Troubleshooting Guide](./operations/TROUBLESHOOTING.md) — Common issues

  - [FAQ](#) — Frequently asked questions

  - [Glossary](#) — Key terms

1. **Review relevant documentation**:

  - Installation issues → [Setup Guide](./operations/SETUP_GUIDE.md)

  - Configuration issues → [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md)

  - Secrets issues → [Vault Setup](./operations/VAULT_SETUP.md)

  - Service issues → [Troubleshooting](./operations/TROUBLESHOOTING.md)

1. **Check logs**:

```bash
   # View service logs
sudo journalctl -u vault -u mariadb -u chromadb -f

   # Check application logs
tail -f logs/*.log ```

1. **Run diagnostics**:

```bash
   # Full health check
bash scripts/run_with_env.sh python check_databases.py

   # Service status
sudo systemctl status vault mariadb chromadb ```

## 📝 Documentation Standards

All documentation follows these standards:

- **YAML frontmatter**: Title, description, optional tags

- **Headers**: H1 for page title, H2+ for sections

- **Code blocks**: Language-tagged for syntax highlighting

- **Tables**: For reference material

- **Internal links**: Relative paths for repo navigation

- **External links**: Full URLs with clear context

---

**Last Updated**: December 15, 2024 **Version**: 4.0.0 **Maintainer**: JustNews Operations Team
