# JustNews Nomad Deployment

This directory contains the HashiCorp Nomad deployment configuration for the JustNews AI system. Nomad provides vendor-neutral, self-hosted container orchestration that maintains independence from corporate cloud providers.

## Overview

The Nomad deployment provides:
- **Self-hosted orchestration**: No dependency on corporate cloud services
- **Multi-datacenter support**: Deploy across geographically distributed locations
- **Service discovery**: Integrated with Consul for automatic service registration
- **GPU support**: Native GPU workload scheduling
- **Infrastructure agnostic**: Runs on any servers you control

## Architecture

### Components
- **Nomad Servers**: Control plane for job scheduling and cluster management
- **Nomad Clients**: Worker nodes that execute tasks
- **Consul**: Service discovery and health checking
- **Docker**: Container runtime for all services

### Services
- **Infrastructure**: PostgreSQL, Redis, Prometheus, Grafana
- **AI Agents**: 15 specialized agents with GPU support for ML workloads
- **Service Mesh**: Consul-based service discovery and load balancing

## Prerequisites

### System Requirements
- **Servers**: 3+ servers for high availability (1-2 for Nomad/Consul servers, rest for workers)
- **OS**: Linux (Ubuntu 20.04+, CentOS 7+, etc.)
- **CPU**: 2+ cores per server
- **RAM**: 4GB+ per server (8GB+ for GPU nodes)
- **Storage**: 50GB+ SSD storage per server
- **Network**: Private network between servers

### Software Requirements
- **Nomad**: Latest stable version
- **Consul**: Latest stable version
- **Docker**: 20.10+
- **NVIDIA Drivers**: For GPU nodes (optional)

## Quick Start

### 1. Prepare Servers

On each server, install required software:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Nomad
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com jammy main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install nomad consul

# Enable and start services
sudo systemctl enable nomad consul docker
sudo systemctl start nomad consul docker
```

### 2. Configure Cluster

**On Server Nodes (nomad-server-01, nomad-server-02, nomad-server-03):**
```bash
sudo cp config/server.hcl /etc/nomad.d/nomad.hcl
sudo cp consul/config/server.hcl /etc/consul.d/consul.hcl
sudo systemctl restart nomad consul
```

**On Client Nodes:**
```bash
sudo cp config/client.hcl /etc/nomad.d/nomad.hcl
sudo cp consul/config/client.hcl /etc/consul.d/consul.hcl
# For GPU nodes, edit /etc/nomad.d/nomad.hcl and set:
# node_class = "gpu-worker"
# meta { gpu_enabled = "true" }
sudo systemctl restart nomad consul
```

### 3. Deploy JustNews

```bash
cd infrastructure/nomad

# Check cluster status
./scripts/deploy.sh check

# Deploy all services
./scripts/deploy.sh deploy

# Monitor deployment
./scripts/monitor.sh all
```

## Configuration

### Environment Variables
Set these in your environment or modify the job files:

```bash
export NOMAD_ADDR=http://your-nomad-server:4646
export CONSUL_ADDR=http://your-consul-server:8500
```

### GPU Configuration
For GPU nodes, ensure:
1. NVIDIA drivers are installed
2. `nvidia-docker2` is installed
3. Nomad client config has GPU enabled
4. Node is labeled as GPU-capable

### Networking
- **Internal**: Services communicate via Consul service discovery
- **External**: Configure load balancers or reverse proxies for external access
- **Security**: Use firewalls to restrict access to management ports

## Management Commands

### Deployment
```bash
# Check cluster health
./scripts/deploy.sh check

# Deploy all services
./scripts/deploy.sh deploy

# Deploy infrastructure only
./scripts/deploy.sh deploy-infra

# Deploy agents only
./scripts/deploy.sh deploy-agents

# Stop all services
./scripts/deploy.sh stop
```

### Monitoring
```bash
# Overall health check
./scripts/monitor.sh health

# Service status
./scripts/monitor.sh services

# Resource usage
./scripts/monitor.sh resources

# GPU status
./scripts/monitor.sh gpu

# Generate report
./scripts/monitor.sh report
```

### Scaling
```bash
# Scale scout agents
./scripts/deploy.sh scale justnews-agents 5

# Check job status
nomad job status justnews-agents
```

### Logs
```bash
# View agent logs
./scripts/deploy.sh logs justnews-agents

# View specific task logs
./scripts/deploy.sh logs justnews-infrastructure postgres
```

## Service Discovery

Services are automatically registered with Consul:
- **PostgreSQL**: `postgres.service.consul:5432`
- **Redis**: `redis.service.consul:6379`
- **MCP Bus**: `mcp-bus.service.consul:8000`
- **Prometheus**: `prometheus.service.consul:9090`
- **Grafana**: `grafana.service.consul:3000`

## Security Considerations

### Production Setup
1. **TLS**: Enable TLS for Nomad and Consul
2. **ACLs**: Configure access control lists
3. **Firewalls**: Restrict management port access
4. **Secrets**: Use Vault for sensitive data (optional)
5. **Updates**: Regular security updates for all components

### Network Security
- Use private networks between servers
- Configure firewall rules
- Enable mTLS for service communication
- Regular security audits

## Troubleshooting

### Common Issues

1. **Jobs not scheduling**: Check node resources and constraints
2. **Services not healthy**: Check Consul connectivity
3. **GPU not available**: Verify NVIDIA drivers and Docker GPU support
4. **Network issues**: Check firewall rules and service discovery

### Logs
```bash
# Nomad logs
sudo journalctl -u nomad -f

# Consul logs
sudo journalctl -u consul -f

# Docker logs
sudo journalctl -u docker -f
```

### Debugging
```bash
# Check node status
nomad node status

# Check allocations
nomad alloc status

# Check Consul services
curl http://localhost:8500/v1/catalog/services
```

## Backup and Recovery

### Data Backup
```bash
# Backup PostgreSQL
nomad alloc exec -job justnews-infrastructure -task postgres pg_dump -U justnews justnews > backup.sql

# Backup Redis
nomad alloc exec -job justnews-infrastructure -task redis redis-cli save

# Backup configurations
cp jobs/*.nomad backup/
cp config/*.hcl backup/
```

### Disaster Recovery
1. Restore server configurations
2. Bootstrap new cluster
3. Restore data volumes
4. Redeploy services

## Performance Tuning

### Resource Allocation
- Adjust CPU/memory limits based on workload
- Monitor resource usage with Prometheus
- Scale services based on demand

### Storage
- Use SSD storage for databases
- Configure volume mounts for persistent data
- Monitor disk usage

### Networking
- Optimize network configuration
- Use host networking for high-performance services
- Configure service mesh for security

## Multi-Region Deployment

For geographic distribution:

1. **Setup multiple datacenters**: Configure separate Nomad/Consul clusters
2. **Federation**: Enable cross-datacenter communication
3. **DNS**: Configure global DNS for service discovery
4. **Load balancing**: Use global load balancers for traffic distribution

## Contributing

When modifying the deployment:
1. Test changes in a staging environment
2. Update documentation
3. Validate with monitoring scripts
4. Follow infrastructure as code principles

## Support

For issues and questions:
- Check Nomad/Consul documentation
- Review logs and monitoring data
- Test in isolated environments
- Document and share findings