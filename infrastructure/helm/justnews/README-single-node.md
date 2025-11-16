# JustNews Single-Node Kubernetes Deployment

This guide shows how to deploy JustNews on a single machine optimized for your AMD Ryzen 7 (16 cores) + 32GB RAM + RTX3090 setup.

## System Requirements Met ✅

Your hardware meets the minimum requirements:
- **CPU**: 16 cores (AMD Ryzen 7) ✅
- **RAM**: 32GB ✅
- **GPU**: RTX3090 (24GB VRAM) ✅
- **Storage**: 50GB+ free space ✅

## Optimized Configuration

The `values-single-node.yaml` includes these optimizations:

### Resource Adjustments
- **CPU limits**: Reduced from 1000m to 500m per agent
- **Memory limits**: Reduced from 2Gi to 1Gi per agent
- **Infrastructure**: Scaled down PostgreSQL, Redis, Prometheus, Grafana

### Agent Selection
### GPU Usage

### Training Features

### Storage

## Quick Start

### 1. Prerequisites
```bash
# Install NVIDIA drivers (if not already installed)
ubuntu-drivers autoinstall

# Install Helm
curl https://get.helm.sh/helm-v3.12.0-linux-amd64.tar.gz -o helm.tar.gz
tar -zxvf helm.tar.gz
sudo mv linux-amd64/helm /usr/local/bin/helm
```

### 2. Deploy Everything
```bash
cd /home/adra/JustNewsAgent-Clean
./infrastructure/helm/justnews/deploy-single-node.sh all
```

This will:
- Check system requirements
- Install k3s (lightweight Kubernetes)
- Setup local storage
- Deploy JustNews with optimized configuration
- Setup port forwarding

### 3. Access JustNews
```
Grafana:    http://localhost:3000 (admin/admin_password)
Prometheus: http://localhost:9090
MCP Bus:    http://localhost:8000
```

## Manual Deployment Steps

If you prefer step-by-step deployment:

```bash
cd /home/adra/JustNewsAgent-Clean

# 1. Check system
./infrastructure/helm/justnews/deploy-single-node.sh check

# 2. Install k3s and dependencies
./infrastructure/helm/justnews/deploy-single-node.sh install

# 3. Optional: Install GPU operator
./infrastructure/helm/justnews/deploy-single-node.sh gpu-setup

This installs the NVIDIA GPU Operator with MPS (Multi-Process Service) support enabled, allowing multiple agents to share the RTX3090 concurrently without context switching overhead.

# 4. Deploy JustNews
./infrastructure/helm/justnews/deploy-single-node.sh deploy

# 5. Check status
./infrastructure/helm/justnews/deploy-single-node.sh status

# 6. Setup port forwarding
./infrastructure/helm/justnews/deploy-single-node.sh ports
```

## Resource Usage Estimate

With the optimized configuration:

### CPU Usage
- **Agents**: 15 × 600m = 9 cores (reduced for OS compatibility)
- **Infrastructure**: ~2.5 cores (PostgreSQL 600m, Redis 300m, Prometheus 500m, Grafana 250m)
- **Total**: ~11.5 cores (72% utilization - good headroom for OS)

### Memory Usage (Accounting for Ubuntu 24.04 + IDE)
- **OS Overhead**: ~4-6GB (Ubuntu 24.04 + VS Code + system buffers)
- **Agents**: 15 × 1.2Gi = 18Gi
- **Infrastructure**: ~4.5Gi
- **Kubernetes**: ~1-2GB overhead
- **Total Estimated**: ~23.5-25.5GB (78-84% utilization - safe within 32GB)

**Memory Safety Notes:**
- Conservative limits account for desktop OS and IDE usage
- ~6-8GB headroom maintained for system stability
- Monitor with `kubectl top nodes` and adjust if needed

### Training Features
- **Online Training**: Enabled for continuous model improvement
- **Training Data Path**: /data/training (local storage)
- **GPU Acceleration**: Training workloads leverage MPS sharing

## Monitoring Resources

Check resource usage:
```bash
# Pod resource usage
kubectl top pods -n justnews

# Node resources
kubectl top nodes

# GPU usage
kubectl get pods -n justnews -o json | jq '.items[].spec.containers[].resources'
```

## Scaling Up

If you want to enable more agents later:

1. **Edit values-single-node.yaml**:
   ```yaml
   synthesizer:
     enabled: true
     replicas: 1
   ```

2. **Upgrade deployment**:
   ```bash
   helm upgrade justnews ./infrastructure/helm/justnews \
        --namespace justnews \
        --values infrastructure/helm/justnews/values-single-node.yaml
   ```

3. **Monitor resources** to ensure you don't exceed limits

## Troubleshooting

### Common Issues

1. **GPU not detected**:
   ```bash
   # Check NVIDIA drivers
   nvidia-smi

   # Check GPU operator
   kubectl get pods -n gpu-operator
   ```

2. **Insufficient resources**:
   ```bash
   # Check resource usage
   kubectl describe nodes

   # Reduce agent resource limits in values-single-node.yaml
   ```

3. **Pods not starting**:
   ```bash
   # Check pod status
   kubectl get pods -n justnews
   kubectl describe pod <pod-name> -n justnews
   ```

4. **Storage issues**:
   ```bash
   # Check persistent volumes
   kubectl get pv,pvc -n justnews
   ```

### Logs
```bash
# Agent logs
kubectl logs -n justnews deployment/justnews-scout

# Infrastructure logs
kubectl logs -n justnews -l app.kubernetes.io/name=postgresql

# System logs
kubectl logs -n kube-system -l component=kubelet
```

## Backup and Recovery

### Backup Data
```bash
# PostgreSQL backup
kubectl exec -n justnews justnews-postgresql-0 -- pg_dump -U justnews justnews > backup.sql

# Redis backup
kubectl exec -n justnews justnews-redis-master-0 -- redis-cli save
```

### Full Cleanup
```bash
./deploy-single-node.sh cleanup
```

## Performance Tuning

### For Better Performance
1. **Monitor actual usage** with `kubectl top` before increasing limits
2. **Consider resource adjustments** only after observing stable operation
3. **All agents are already GPU-enabled** with MPS sharing for optimal performance

### For Lower Resource Usage
1. **Reduce agent replicas** to 1 each
2. **Disable non-essential agents** (analytics, dashboard)
3. **Use smaller resource requests/limits**
4. **Disable persistence** for development

## Next Steps

Once running on single node, you can:

1. **Test functionality** with sample data
2. **Monitor performance** via Grafana dashboards
3. **Scale up** by enabling more agents
4. **Plan multi-node deployment** for production
5. **Add ingress/load balancer** for external access

## Hardware Upgrade Path

If you need more capacity:
- **Add RAM**: 64GB+ for more agents
- **Add GPU**: RTX 3090 Ti or RTX 4090 for more GPU agents
- **Add storage**: NVMe SSDs for better performance
- **Multi-node**: Add more servers for horizontal scaling