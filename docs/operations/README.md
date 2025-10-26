# JustNewsAgent Operations Guide

## Deployment Procedures

This guide covers production deployment, scaling, and operational procedures for JustNewsAgent.

## Environment Overview

### Development Environment
- **Purpose**: Feature development and testing
- **Components**: Docker Compose with hot reload
- **Persistence**: Local volumes and SQLite
- **Monitoring**: Basic logging and health checks

### Staging Environment
- **Purpose**: Integration testing and validation
- **Components**: Kubernetes with 2-3 replicas
- **Persistence**: PostgreSQL with test data
- **Monitoring**: Prometheus/Grafana dashboards

### Production Environment
- **Purpose**: Live system serving real traffic
- **Components**: Kubernetes with auto-scaling
- **Persistence**: PostgreSQL cluster with backups
- **Monitoring**: Full observability stack

## Prerequisites

### System Requirements
```bash
# Minimum hardware requirements
- CPU: 8 cores
- RAM: 32GB
- GPU: NVIDIA RTX 3090 or equivalent (24GB VRAM)
- Storage: 500GB SSD
- Network: 1Gbps connection

# Software requirements
- Kubernetes 1.25+
- NVIDIA GPU Operator
- PostgreSQL 15+
- Redis 7+
- Docker 24+
```

### Network Configuration
```yaml
# Required ports (internal)
8000: MCP Bus
8001-8008: Agent services
8013: Dashboard
8014: Public API
8020: GraphQL API
8021: Archive API

# External access
80/443: Web interface and APIs
```

## Deployment Methods

### Method 1: Kubernetes (Recommended)

#### Prerequisites
```bash
# Install kubectl and helm
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Install helm
curl https://get.helm.sh/helm-v3.12.0-linux-amd64.tar.gz | tar -xz
sudo mv linux-amd64/helm /usr/local/bin/
```

#### Deploy Infrastructure
```bash
# Create namespace
kubectl create namespace justnews

# Deploy PostgreSQL
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgres bitnami/postgresql \
  --namespace justnews \
  --set auth.postgresPassword=your_password

# Deploy Redis
helm install redis bitnami/redis \
  --namespace justnews \
  --set auth.password=your_password
```

#### Deploy JustNewsAgent
```bash
# Clone repository
git clone <repository>
cd JustNewsAgent

# Deploy to Kubernetes
kubectl apply -f deploy/kubernetes/production/

# Verify deployment
kubectl get pods -n justnews
kubectl get services -n justnews
```

#### Configuration
```bash
# Create secrets
kubectl create secret generic justnews-secrets \
  --namespace justnews \
  --from-literal=database-url=postgresql://... \
  --from-literal=redis-url=redis://... \
  --from-literal=api-keys=...

# Apply configuration
kubectl apply -f config/kubernetes/
```

### Method 2: Docker Compose (Development/Staging)

#### Quick Start
```bash
# Clone repository
git clone <repository>
cd JustNewsAgent

# Start all services
docker-compose -f docker-compose.yml up -d

# Check status
docker-compose ps
docker-compose logs -f
```

#### Production-Ready Compose
```bash
# Use production compose file
docker-compose -f docker-compose.prod.yml up -d

# Scale services
docker-compose up -d --scale scout=3 --scale analyst=2
```

### Method 3: systemd (Legacy)

#### Systemd Deployment
```bash
# Install systemd services
sudo cp infrastructure/systemd/units/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start services in order
sudo systemctl start justnews-mcp-bus
sudo systemctl start justnews-postgres
sudo systemctl start justnews-redis

# Start agents
for service in justnews-scout justnews-analyst justnews-synthesizer; do
  sudo systemctl start $service
done

# Enable auto-start
sudo systemctl enable justnews-*
```

## Scaling Procedures

### Horizontal Scaling

#### Kubernetes Auto-scaling
```yaml
# HPA configuration
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: scout-agent-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: scout-agent
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

#### Manual Scaling
```bash
# Scale via kubectl
kubectl scale deployment scout-agent --replicas=5

# Scale via docker-compose
docker-compose up -d --scale scout=5
```

### Vertical Scaling

#### GPU Scaling
```bash
# Check GPU utilization
nvidia-smi

# Scale GPU resources
kubectl patch deployment analyst-agent \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/nvidia.com~1gpu", "value": "2"}]'
```

#### Memory/CPU Scaling
```bash
# Update resource requests/limits
kubectl set resources deployment synthesizer-agent \
  --limits=cpu=2,memory=8Gi \
  --requests=cpu=1,memory=4Gi
```

## Monitoring & Alerting

### Health Checks

#### Service Health
```bash
# Check all services
curl http://localhost:8000/health
curl http://localhost:8001/health
# ... check all agent health endpoints

# Kubernetes health
kubectl get pods -n justnews
kubectl describe pod <pod-name>
```

#### Application Metrics
```bash
# Prometheus metrics
curl http://localhost:9090/metrics

# Custom metrics
curl http://localhost:8000/metrics
curl http://localhost:8004/metrics  # GPU metrics
```

### Alerting Configuration

#### Prometheus Alerts
```yaml
groups:
- name: justnews_alerts
  rules:
  - alert: HighCPUUsage
    expr: cpu_usage_percent > 85
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High CPU usage detected"

  - alert: GPUOutOfMemory
    expr: gpu_memory_used_percent > 95
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "GPU memory critically high"
```

#### Dashboard Access
```bash
# Grafana dashboard
open http://localhost:3000

# Application dashboard
open http://localhost:8013
```

## Backup & Recovery

### Database Backup
```bash
# PostgreSQL backup
pg_dump -h localhost -U justnews -d justnews_db > backup_$(date +%Y%m%d).sql

# Automated backup script
./scripts/backup_database.sh
```

### Configuration Backup
```bash
# Backup configs
tar -czf config_backup_$(date +%Y%m%d).tar.gz config/

# Kubernetes config backup
kubectl get all -n justnews -o yaml > k8s_backup.yaml
```

### Recovery Procedures

#### Database Recovery
```bash
# Stop all services
kubectl scale deployment --all --replicas=0 -n justnews

# Restore database
psql -h localhost -U justnews -d justnews_db < backup_file.sql

# Restart services
kubectl scale deployment --all --replicas=1 -n justnews
```

#### Full System Recovery
```bash
# Complete recovery script
./scripts/disaster_recovery.sh

# Verify recovery
make health-check
make test-integration
```

## Security Operations

### Access Control
```bash
# Rotate API keys
./scripts/rotate_api_keys.sh

# Update certificates
./scripts/update_certificates.sh

# Security audit
./scripts/security_audit.sh
```

### Compliance Monitoring
```bash
# GDPR compliance check
./scripts/gdpr_audit.sh

# Data retention cleanup
./scripts/data_cleanup.sh

# Audit log review
./scripts/review_audit_logs.sh
```

## Troubleshooting

### Common Issues

#### Service Startup Failures
```bash
# Check service logs
kubectl logs -f deployment/mcp-bus -n justnews

# Check events
kubectl get events -n justnews --sort-by=.metadata.creationTimestamp

# Check resource constraints
kubectl describe pod <pod-name>
```

#### Performance Issues
```bash
# Check resource usage
kubectl top pods -n justnews

# Check GPU usage
nvidia-smi

# Profile application
./scripts/profile_performance.sh
```

#### Network Issues
```bash
# Check service connectivity
kubectl exec -it <pod-name> -- curl http://localhost:8000/health

# Check network policies
kubectl get networkpolicies -n justnews

# DNS resolution
kubectl exec -it <pod-name> -- nslookup mcp-bus
```

## Maintenance Windows

### Scheduled Maintenance
```bash
# Enter maintenance mode
./scripts/maintenance_mode.sh enable

# Perform maintenance
# ... maintenance tasks ...

# Exit maintenance mode
./scripts/maintenance_mode.sh disable
```

### Rolling Updates
```bash
# Update with zero downtime
kubectl set image deployment/scout-agent scout-agent=scout-agent:v2.0.0

# Monitor rollout
kubectl rollout status deployment/scout-agent

# Rollback if needed
kubectl rollout undo deployment/scout-agent
```

---

*Operations Guide Version: 1.0.0*
*Last Updated: October 22, 2025*