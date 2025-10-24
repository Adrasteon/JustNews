# JustNews Docker Swarm Deployment

This directory contains the Docker Swarm deployment configuration for the JustNews AI system.

## Overview

The Docker Swarm deployment provides clustering capabilities for production environments, with built-in service discovery, load balancing, and high availability features.

## Architecture

- **19 services**: 15 AI agents + 4 infrastructure services (PostgreSQL, Redis, Prometheus, Grafana)
- **Secrets management**: Docker secrets for sensitive data
- **Configuration management**: Docker configs for non-sensitive configuration
- **Overlay networking**: Service-to-service communication
- **GPU support**: Node labeling and placement constraints for GPU workloads
- **Service replication**: Horizontal scaling with configurable replicas

## Prerequisites

- Docker Engine with Swarm mode enabled
- At least 3 nodes (1 manager, 2 workers) for high availability
- GPU nodes labeled for GPU workloads (optional)
- Minimum 16GB RAM, 4 CPU cores per node

## Quick Start

1. **Initialize Swarm** (on manager node):
   ```bash
   docker swarm init
   ```

2. **Join worker nodes** (on each worker node):
   ```bash
   docker swarm join --token <worker-token> <manager-ip>:2377
   ```

3. **Label GPU nodes** (if you have GPU nodes):
   ```bash
   docker node update --label-add gpu=true <node-name>
   ```

4. **Deploy the stack**:
   ```bash
   cd infrastructure/docker-swarm
   ./scripts/deploy.sh init
   ./scripts/deploy.sh deploy
   ```

## Configuration

### Environment Variables

Edit `.env.swarm` to configure:
- Database passwords
- Grafana admin credentials
- Service replica counts
- Resource limits
- Network settings

### Secrets

Create required secrets before deployment:
```bash
echo "your_postgres_password" | docker secret create postgres_password -
echo "your_redis_password" | docker secret create redis_password -
echo "your_grafana_password" | docker secret create grafana_admin_password -
```

### Scaling Services

Scale individual services:
```bash
docker service scale justnews_scout=3 justnews_memory=2
```

Or use the deployment script:
```bash
./scripts/deploy.sh scale scout 3
```

## Monitoring

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Service status**: `docker service ls`

## Management Commands

```bash
# Check deployment status
./scripts/deploy.sh status

# View service logs
docker service logs justnews_scout

# Update service image
docker service update --image new-image:tag justnews_scout

# Rolling update
./scripts/deploy.sh update

# Scale services
./scripts/deploy.sh scale scout 5

# Backup data
./scripts/deploy.sh backup

# Cleanup deployment
./scripts/deploy.sh cleanup
```

## Troubleshooting

### Common Issues

1. **Service won't start**: Check resource constraints and node labels
2. **Network issues**: Verify overlay network creation
3. **GPU not available**: Ensure GPU nodes are properly labeled
4. **Secrets not found**: Create secrets before deployment

### Logs

```bash
# Service logs
docker service logs justnews_scout

# Swarm logs
docker swarm ps justnews_scout

# Node status
docker node ls
```

## Production Considerations

- Use external load balancer for high availability
- Configure backup and recovery procedures
- Set up monitoring alerts
- Implement log aggregation
- Configure TLS certificates
- Regular security updates

## Backup and Recovery

The deployment script includes backup functionality:
```bash
./scripts/deploy.sh backup
```

This creates backups of:
- PostgreSQL database
- Redis data
- Grafana dashboards and configurations
- Service configurations

## Security

- All sensitive data stored as Docker secrets
- Non-root user execution in containers
- Network segmentation with overlay networks
- Regular secret rotation recommended

## Performance Tuning

- Adjust replica counts based on load
- Configure resource limits appropriately
- Use SSD storage for databases
- Monitor resource usage and scale accordingly