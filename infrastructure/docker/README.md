# JustNews Docker Deployment

This directory contains the complete Docker deployment configuration for the JustNews AI agent system.

## Overview

The Docker deployment includes:
- **15 AI Agents**: All JustNews agents containerized and ready to deploy
- **Databases**: PostgreSQL and Redis with persistent storage
- **Monitoring**: Prometheus and Grafana for observability
- **MCP Bus**: Communication hub for inter-agent coordination
- **GPU Support**: GPU-enabled agents with NVIDIA Docker support

## Prerequisites

- Docker and Docker Compose
- At least 8GB RAM recommended
- For GPU support: NVIDIA Docker runtime and compatible GPU

## Quick Start

1. **Clone and navigate to the project**:
   ```bash
   cd /path/to/JustNewsAgent-Clean
   ```

2. **Configure environment**:
   ```bash
   cd infrastructure/docker
   cp .env.example .env
   # Edit .env with your secure passwords
   ```

3. **Start the deployment**:
   ```bash
   docker-compose up -d
   ```

4. **Check status**:
   ```bash
   docker-compose ps
   ```

5. **View logs**:
   ```bash
   docker-compose logs -f [service-name]
   ```

## Services

### Core Services
- **postgres**: Database (port 5432)
- **redis**: Cache (port 6379)
- **mcp-bus**: Communication hub (port 8000)

### AI Agents (CPU)
- **scout**: Web crawling and content discovery (port 8002)
- **chief-editor**: Content orchestration (port 8001)
- **memory**: Knowledge storage (port 8007)
- **reasoning**: Logical analysis (port 8008)
- **critic**: Quality assessment (port 8006)
- **dashboard**: User interface (port 8013)
- **analytics**: Data analysis (port 8011)
- **archive**: Content storage (port 8012)
- **balancer**: Load distribution (port 8010)
- **gpu-orchestrator**: GPU resource management (port 8015)

### AI Agents (GPU-enabled)
- **analyst**: Quantitative analysis (port 8004) - *Requires GPU*
- **synthesizer**: Content synthesis (port 8005) - *Requires GPU*
- **fact-checker**: Fact verification (port 8003) - *Requires GPU*
- **newsreader**: Content processing (port 8009) - *Requires GPU*

### Monitoring
- **prometheus**: Metrics collection (port 9090)
- **grafana**: Visualization dashboard (port 3000)

## GPU Support

For GPU-enabled agents, ensure you have:
- NVIDIA GPU with CUDA support
- NVIDIA Docker runtime installed
- GPU-enabled Docker images will be automatically used

## Configuration

### Environment Variables
Edit the `.env` file to configure:
- Database passwords
- Grafana admin credentials
- Logging levels
- External URLs

### Scaling
To scale specific services:
```bash
docker-compose up -d --scale analyst=3
```

### Health Checks
All services include health checks. Monitor with:
```bash
docker-compose ps
```

## Monitoring

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Agent APIs**: Available on their respective ports

## Troubleshooting

### Common Issues

1. **Port conflicts**: Change ports in docker-compose.yml
2. **GPU not detected**: Ensure NVIDIA runtime is installed
3. **Memory issues**: Increase Docker memory limits
4. **Database connection**: Check POSTGRES_PASSWORD in .env

### Logs
```bash
# All services
docker-compose logs

# Specific service
docker-compose logs mcp-bus

# Follow logs
docker-compose logs -f analyst
```

### Cleanup
```bash
# Stop and remove containers
docker-compose down

# Remove volumes (WARNING: deletes data)
docker-compose down -v
```

## Development

### Building Custom Images
```bash
docker-compose build [service-name]
```

### Accessing Containers
```bash
docker-compose exec [service-name] bash
```

### Updating Agents
```bash
# Rebuild all agents
docker-compose build

# Rebuild specific agent
docker-compose build analyst
```

## Production Deployment

For production:
1. Use external databases
2. Configure proper secrets management
3. Set up reverse proxy (nginx/traefik)
4. Configure TLS certificates
5. Set up backup strategies
6. Configure resource limits

## Architecture

```
┌─────────────────┐    ┌─────────────────┐
│   Web Clients   │────│   Dashboard     │
│                 │    │   (Port 8013)   │
└─────────────────┘    └─────────────────┘
                              │
                              ▼
┌─────────────────┐    ┌─────────────────┐
│   MCP Bus       │◄──►│   AI Agents     │
│   (Port 8000)   │    │   (Ports 8001+) │
└─────────────────┘    └─────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐    ┌─────────────────┐
│   PostgreSQL    │    │   Monitoring    │
│   (Port 5432)   │    │   Stack         │
└─────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│     Redis       │
│   (Port 6379)   │
└─────────────────┘
```

## Support

For issues or questions:
1. Check the logs: `docker-compose logs`
2. Verify configuration in `.env`
3. Ensure sufficient system resources
4. Check Docker and Docker Compose versions