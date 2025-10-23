# JustNews Deployment System - Unified Infrastructure as Code

Enterprise-grade deployment framework supporting Docker, Kubernetes, and systemd orchestration for the JustNewsAgent distributed system.

## Overview

The deployment system provides a unified approach to deploying JustNewsAgent across different environments and platforms. It supports:

- **Docker Compose**: Development and testing environments
- **Kubernetes**: Production container orchestration
- **Systemd**: Traditional service management (legacy support)
- **Infrastructure as Code**: Declarative configuration management
- **Multi-environment**: Development, staging, production profiles

## Architecture

```
deploy/refactor/
├── docker/                    # Docker Compose deployments
│   ├── docker-compose.yml     # Main compose file
│   ├── docker-compose.prod.yml # Production overrides
│   ├── docker-compose.dev.yml  # Development overrides
│   └── Dockerfile.*           # Service-specific Dockerfiles
├── kubernetes/               # Kubernetes manifests
│   ├── base/                 # Base manifests
│   ├── overlays/             # Environment-specific overlays
│   └── kustomization.yml     # Kustomize configuration
├── systemd/                  # Systemd service files (legacy)
│   ├── services/             # Service unit files
│   └── timers/               # Timer units
├── scripts/                  # Deployment automation
│   ├── deploy.sh             # Unified deployment script
│   ├── health-check.sh       # Service health validation
│   └── rollback.sh           # Deployment rollback
├── config/                   # Configuration templates
│   ├── environments/         # Environment-specific configs
│   └── secrets/              # Secret management templates
└── templates/                # Jinja2 templates
    ├── docker-compose.j2     # Docker Compose templates
    ├── k8s-deployment.j2     # Kubernetes deployment templates
    └── systemd-service.j2    # Systemd service templates
```

## Quick Start

### 1. Choose Deployment Target

```bash
# For development (Docker Compose)
export DEPLOY_TARGET=docker-compose
export DEPLOY_ENV=development

# For production (Kubernetes)
export DEPLOY_TARGET=kubernetes
export DEPLOY_ENV=production

# For legacy (systemd)
export DEPLOY_TARGET=systemd
export DEPLOY_ENV=production
```

### 2. Configure Environment

```bash
# Copy and customize environment configuration
cp config/environments/production.env.example config/environments/production.env
nano config/environments/production.env

# Required variables:
# - POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD
# - REDIS_HOST, REDIS_PASSWORD
# - GPU_ORCHESTRATOR_HOST
# - MCP_BUS_HOST, MCP_BUS_PORT
# - LOG_LEVEL, MONITORING_ENABLED
```

### 3. Deploy Services

```bash
# Deploy all services
./scripts/deploy.sh --target $DEPLOY_TARGET --env $DEPLOY_ENV

# Deploy specific service
./scripts/deploy.sh --target $DEPLOY_TARGET --env $DEPLOY_ENV --service mcp-bus

# Check deployment status
./scripts/health-check.sh

# Rollback if needed
./scripts/rollback.sh --target $DEPLOY_TARGET
```

## Service Architecture

### Core Services

| Service | Type | Ports | Description |
|---------|------|-------|-------------|
| **mcp-bus** | FastAPI | 8000 | Central communication hub |
| **scout** | FastAPI + GPU | 8002 | Content discovery and analysis |
| **analyst** | FastAPI + GPU | 8004 | Sentiment and bias analysis |
| **synthesizer** | FastAPI + GPU | 8005 | Content synthesis and clustering |
| **fact-checker** | FastAPI + GPU | 8003 | Evidence-based verification |
| **memory** | FastAPI | 8007 | Vector storage and retrieval |
| **chief-editor** | FastAPI | 8001 | Workflow orchestration |
| **reasoning** | FastAPI | 8008 | Symbolic logic processing |
| **newsreader** | FastAPI + GPU | 8009 | OCR and visual analysis |
| **critic** | FastAPI | 8006 | Quality assessment |
| **dashboard** | FastAPI | 8013 | Web monitoring interface |
| **analytics** | FastAPI | 8011 | Advanced analytics engine |
| **archive** | FastAPI | 8012 | Document storage and retrieval |
| **balancer** | FastAPI | 8010 | Load balancing and routing |

### Infrastructure Services

| Service | Type | Ports | Description |
|---------|------|-------|-------------|
| **postgresql** | Database | 5432 | Primary data storage |
| **redis** | Cache | 6379 | Session and cache storage |
| **grafana** | Monitoring | 3000 | Dashboard and visualization |
| **prometheus** | Monitoring | 9090 | Metrics collection |
| **nginx** | Reverse Proxy | 80/443 | Load balancing and SSL |

## Deployment Targets

### Docker Compose (Development)

```bash
# Start development environment
cd docker/
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f mcp-bus

# Scale services
docker-compose up -d --scale scout=3 --scale analyst=2
```

### Kubernetes (Production)

```bash
# Apply base manifests
kubectl apply -k kubernetes/

# Check pod status
kubectl get pods -l app=justnews

# View logs
kubectl logs -l app=mcp-bus

# Scale deployment
kubectl scale deployment scout --replicas=5
```

### Systemd (Legacy)

```bash
# Install services
sudo cp systemd/services/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start all services
sudo systemctl start justnews-*

# Check status
sudo systemctl status justnews-mcp-bus
```

## Configuration Management

### Environment Variables

```bash
# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=justnews
POSTGRES_USER=justnews
POSTGRES_PASSWORD=secure_password

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=secure_password

# GPU Configuration
GPU_ORCHESTRATOR_HOST=localhost
GPU_ORCHESTRATOR_PORT=8014
CUDA_VISIBLE_DEVICES=0,1,2,3

# MCP Bus Configuration
MCP_BUS_HOST=localhost
MCP_BUS_PORT=8000

# Monitoring Configuration
GRAFANA_ADMIN_PASSWORD=admin_password
PROMETHEUS_RETENTION_TIME=30d

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Secrets Management

```bash
# Using Kubernetes secrets
kubectl create secret generic justnews-secrets \
  --from-literal=postgres-password=secure_password \
  --from-literal=redis-password=secure_password \
  --from-literal=grafana-admin-password=admin_password

# Using Docker secrets
echo "secure_password" | docker secret create postgres_password -
```

## Service Dependencies

```
mcp-bus (8000) ←─┐
                   ├── scout (8002)
                   ├── analyst (8004)
postgresql (5432) ←─┼── synthesizer (8005)
redis (6379) ←─────┼── fact-checker (8003)
                   ├── memory (8007)
                   ├── chief-editor (8001)
                   ├── reasoning (8008)
                   ├── newsreader (8009)
                   └── critic (8006)

dashboard (8013) ←─┼── analytics (8011)
                   ├── archive (8012)
                   └── balancer (8010)

grafana (3000) ←── prometheus (9090)
nginx (80/443) ←───┼── all FastAPI services
```

## Health Checks and Monitoring

### Service Health Checks

```bash
# Check all services
./scripts/health-check.sh

# Check specific service
curl http://localhost:8000/health
curl http://localhost:8002/health

# Kubernetes health checks
kubectl get pods
kubectl describe pod <pod-name>
```

### Monitoring Integration

```bash
# Access Grafana
open http://localhost:3000

# Access Prometheus
open http://localhost:9090

# View service metrics
curl http://localhost:8000/metrics
```

## Scaling and Performance

### Horizontal Scaling

```bash
# Kubernetes HPA (Horizontal Pod Autoscaler)
kubectl autoscale deployment scout --cpu-percent=70 --min=1 --max=10

# Docker Compose scaling
docker-compose up -d --scale scout=5 --scale analyst=3
```

### Resource Management

```yaml
# Kubernetes resource limits
apiVersion: apps/v1
kind: Deployment
metadata:
  name: analyst
spec:
  template:
    spec:
      containers:
      - name: analyst
        resources:
          limits:
            nvidia.com/gpu: 1
            memory: 8Gi
            cpu: 2000m
          requests:
            memory: 4Gi
            cpu: 1000m
```

### GPU Management

```bash
# GPU resource allocation
export CUDA_VISIBLE_DEVICES=0,1,2,3
export GPU_MEMORY_FRACTION=0.8

# Kubernetes GPU scheduling
spec:
  template:
    spec:
      containers:
      - resources:
          limits:
            nvidia.com/gpu: 2
```

## Backup and Recovery

### Database Backup

```bash
# PostgreSQL backup
pg_dump -h localhost -U justnews justnews > backup_$(date +%Y%m%d_%H%M%S).sql

# Redis backup
redis-cli save
```

### Deployment Rollback

```bash
# Rollback Kubernetes deployment
kubectl rollout undo deployment/scout

# Rollback Docker Compose
docker-compose down
docker-compose pull  # Get previous images
docker-compose up -d
```

## Troubleshooting

### Common Issues

1. **Service Startup Failures**
   ```bash
   # Check logs
   kubectl logs -l app=mcp-bus
   docker-compose logs mcp-bus

   # Check dependencies
   ./scripts/health-check.sh
   ```

2. **Database Connection Issues**
   ```bash
   # Test connection
   psql -h localhost -U justnews -d justnews

   # Check service status
   sudo systemctl status postgresql
   kubectl get pods -l app=postgresql
   ```

3. **GPU Resource Conflicts**
   ```bash
   # Check GPU usage
   nvidia-smi

   # Check GPU orchestrator
   curl http://localhost:8014/health
   ```

4. **Network Connectivity**
   ```bash
   # Test service communication
   curl http://localhost:8000/agents
   kubectl exec -it <pod-name> -- curl http://mcp-bus:8000/health
   ```

### Debug Commands

```bash
# Full system status
./scripts/deploy.sh --status

# Service dependency check
./scripts/health-check.sh --dependencies

# Resource utilization
kubectl top pods
docker stats
```

## Security Considerations

- **Network Security**: Service mesh with mTLS encryption
- **Secret Management**: Kubernetes secrets or external vault
- **Access Control**: RBAC for Kubernetes and service-level auth
- **Image Security**: Container scanning and signed images
- **Compliance**: GDPR, SOC2 compliance configurations

## Performance Benchmarks

- **Startup Time**: <30 seconds for full system
- **Service Discovery**: <1 second for agent registration
- **Horizontal Scaling**: <60 seconds for pod scaling
- **Failover**: <10 seconds for service recovery
- **GPU Allocation**: <5 seconds for GPU resource assignment

## Migration Guide

### From Systemd to Kubernetes

1. **Backup current configuration**
   ```bash
   ./scripts/backup-config.sh
   ```

2. **Generate Kubernetes manifests**
   ```bash
   ./scripts/generate-k8s.sh
   ```

3. **Deploy to Kubernetes**
   ```bash
   kubectl apply -k kubernetes/
   ```

4. **Verify migration**
   ```bash
   ./scripts/health-check.sh --target kubernetes
   ```

5. **Remove systemd services**
   ```bash
   sudo systemctl stop justnews-*
   sudo systemctl disable justnews-*
   ```

### From Docker Compose to Kubernetes

1. **Export current state**
   ```bash
   docker-compose config > current-config.yml
   ```

2. **Generate Kubernetes manifests**
   ```bash
   kompose convert -f docker-compose.yml
   ```

3. **Apply Kubernetes manifests**
   ```bash
   kubectl apply -f .
   ```

4. **Update ingress and services**
   ```bash
   kubectl apply -f kubernetes/ingress.yml
   ```

## Contributing

1. **Add new services**: Update templates and manifests
2. **Modify configurations**: Use environment-specific overlays
3. **Test deployments**: Validate across all target platforms
4. **Update documentation**: Keep deployment guides current

## Support

For deployment issues:
1. Check service logs and health endpoints
2. Verify configuration and environment variables
3. Test network connectivity between services
4. Review resource allocation and scaling settings
5. Check platform-specific documentation (Docker, Kubernetes, systemd)</content>
<parameter name="filePath">/home/adra/JustNewsAgent/deploy/refactor/README.md