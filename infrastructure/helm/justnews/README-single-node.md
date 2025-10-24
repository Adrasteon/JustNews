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
- **Enabled**: 10 core agents (non-GPU intensive)
- **GPU-enabled**: 2 agents (scout, analyst) - fits single RTX3090
- **Disabled**: 3 GPU agents (synthesizer, fact-checker, newsreader) to prevent GPU contention

### Storage
- **Local storage**: Uses `local-path` provisioner instead of cloud storage
- **Reduced sizes**: Smaller persistent volumes for single-node setup

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
cd infrastructure/helm/justnews
./deploy-single-node.sh all
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
# 1. Check system
./deploy-single-node.sh check

# 2. Install k3s and dependencies
./deploy-single-node.sh install

# 3. Optional: Install GPU operator
./deploy-single-node.sh gpu-setup

# 4. Deploy JustNews
./deploy-single-node.sh deploy

# 5. Check status
./deploy-single-node.sh status

# 6. Setup port forwarding
./deploy-single-node.sh ports
```

## Resource Usage Estimate

With the optimized configuration:

### CPU Usage
- **Agents**: 10 × 500m = 5 cores
- **Infrastructure**: ~2 cores
- **Total**: ~7 cores (well within 16-core limit)

### Memory Usage
- **Agents**: 10 × 1Gi = 10Gi
- **Infrastructure**: ~4Gi
- **Total**: ~14Gi (comfortable within 32Gi limit)

### GPU Usage
- **Active GPU agents**: 2 (scout, analyst)
- **GPU memory**: ~8-12GB (well within 24GB RTX3090 limit)

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
1. **Increase resource limits** if you have spare capacity
2. **Use SSD storage** for better database performance
3. **Enable online training** in values file
4. **Add more GPU agents** if GPU memory allows

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