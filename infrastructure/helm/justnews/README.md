# JustNews Helm Chart

This Helm chart deploys the complete JustNews AI agent system on Kubernetes, including all 15 specialized agents, databases, monitoring stack, and supporting infrastructure.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- NVIDIA GPU Operator (if GPU support is enabled)
- StorageClass for persistent volumes

## Installing the Chart

To install the chart with the release name `justnews`:

```bash
helm install justnews ./infrastructure/helm/justnews
```

## Configuration

The following table lists the configurable parameters of the JustNews chart and their default values.

### Global JustNews Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `justnews.image.registry` | Global Docker image registry | `localhost:5000` |
| `justnews.image.tag` | Global Docker image tag | `latest` |
| `justnews.logLevel` | Logging level | `INFO` |
| `justnews.environment` | Environment name | `production` |
| `justnews.debug` | Enable debug mode | `false` |
| `justnews.gpu.enabled` | Enable GPU support | `true` |
| `justnews.gpu.memoryFraction` | GPU memory fraction | `0.8` |

### Agent Configuration

Each agent can be configured individually. The chart supports 15 agents:

- analyst
- analytics
- archive
- auth
- balancer
- chief_editor
- common
- crawler
- crawler_control
- critic
- dashboard
- fact_checker
- gpu_orchestrator
- memory
- newsreader
- reasoning
- scout
- synthesizer

Example agent configuration:

```yaml
justnews:
  agents:
  - name: analyst
    port: 8001
    replicas: 2
    gpuRequired: true
    minReplicas: 1
    maxReplicas: 5
```

### Database Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `postgres.database` | PostgreSQL database name | `justnews` |
| `postgres.auth.username` | PostgreSQL username | `justnews` |
| `postgres.auth.password` | PostgreSQL password | Random |
| `redis.auth.password` | Redis password | Random |

### Monitoring Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `prometheus.replicas` | Prometheus replicas | `1` |
| `grafana.adminUser` | Grafana admin username | `admin` |
| `grafana.adminPassword` | Grafana admin password | Random |

### Ingress Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `nginx` |
| `ingress.hosts[0].host` | Ingress host | `justnews.local` |

## Example Configuration

```yaml
justnews:
  environment: production
  gpu:
    enabled: true
  agents:
  - name: analyst
    port: 8001
    replicas: 2
    gpuRequired: true
  - name: crawler
    port: 8002
    replicas: 3
    gpuRequired: false

postgres:
  auth:
    password: "my-secret-password"

ingress:
  enabled: true
  hosts:
  - host: justnews.example.com
    paths:
    - path: /
      pathType: Prefix
      service:
        name: justnews-grafana
        port: 3000
```

## GPU Support

The chart includes comprehensive GPU support:

- Automatic node selection for GPU-required agents
- NVIDIA GPU resource allocation
- GPU memory fraction configuration
- Taints and tolerations for GPU nodes

## Monitoring and Observability

The chart includes:

- **Prometheus**: Metrics collection from all services
- **Grafana**: Visualization dashboards
- **Health checks**: Liveness and readiness probes for all services
- **Auto-scaling**: Horizontal Pod Autoscalers based on CPU/memory usage

## Security Features

- **Network Policies**: Traffic isolation between components
- **RBAC**: Role-based access control
- **Secrets Management**: Secure storage of sensitive data
- **Service Accounts**: Minimal privilege service accounts

## Scaling

The chart supports:

- **Horizontal Pod Autoscaling**: Automatic scaling based on resource usage
- **Manual scaling**: Configure replica counts per component
- **GPU-aware scaling**: Different scaling policies for GPU vs CPU agents

## Persistence

All stateful components include persistent volume claims:

- PostgreSQL data
- Redis data
- Prometheus metrics
- Grafana dashboards and configuration

## Testing

Run the included tests:

```bash
helm test justnews
```

## Upgrading

To upgrade the chart:

```bash
helm upgrade justnews ./infrastructure/helm/justnews
```

## Uninstalling

To uninstall the chart:

```bash
helm uninstall justnews
```

## Troubleshooting

### Common Issues

1. **GPU not available**: Ensure NVIDIA GPU Operator is installed
2. **Storage issues**: Check StorageClass availability
3. **Network connectivity**: Verify NetworkPolicies allow required traffic
4. **Resource constraints**: Check resource limits and requests

### Logs

View logs for specific components:

```bash
kubectl logs -l app=analyst
kubectl logs -l app=postgres
```

### Monitoring

Access Grafana at: `http://<ingress-host>/grafana`

Default credentials: admin / (password from secrets)