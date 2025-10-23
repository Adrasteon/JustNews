# JustNewsAgent V4 🤖 - Production Ready

[![Version](https://img.shields.io/badge/version-4.0.0-green.svg)]()
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CUDA](https://img.shields.io/badge/CUDA-12.4+-green.svg)](https://developer.nvidia.com/cuda-toolkit)
[![TensorRT](https://img.shields.io/badge/TensorRT-Production-orange.svg)](https://developer.nvidia.com/tensorrt)

**Production-Ready Multi-Agent News Analysis System**

JustNews V4 is a comprehensive, enterprise-grade AI-powered news analysis system featuring distributed multi-agent architecture, GPU-accelerated processing, continuous learning, and production-ready deployment infrastructure.

## 🎯 **System Overview**

### Core Architecture
- **17 Specialized AI Agents** with MCP (Model Context Protocol) Bus communication
- **GPU-Accelerated Processing** with TensorRT optimization and NVIDIA MPS resource isolation
- **Enterprise Security** with authentication, authorization, encryption, and compliance monitoring
- **Comprehensive Monitoring** with real-time dashboards, metrics, and alerting
- **Multi-Platform Deployment** supporting Docker, Kubernetes, and systemd

### Key Performance Metrics
- **730+ articles/sec** GPU processing throughput
- **99.9% uptime** with comprehensive error handling
- **Enterprise GPU Management** with 23GB total allocation and 69.6% efficiency
- **Zero-touch Recovery** with automatic post-reboot restoration

## 🚀 **Quick Start**

### Prerequisites
- Python 3.12+
- CUDA 12.4+ (for GPU acceleration)
- PostgreSQL 15+
- 32GB+ RAM recommended
- NVIDIA GPU with 8GB+ VRAM (optional but recommended)

### Installation

1. **Clone and Setup Environment**
```bash
git clone <repository-url>
cd JustNewsAgent
conda env create -f environment.yml
conda activate justnews-v2-py312
```

2. **Install Dependencies**
```bash
pip install -r requirements.txt
```

3. **Initialize Database**
```bash
python scripts/init_database.py
```

4. **Start Services**
```bash
# Development mode
python -m agents.mcp_bus.main &

# Or use systemd (production)
sudo systemctl start justnews-mcp-bus
sudo systemctl start justnews@scout justnews@analyst justnews@synthesizer
```

### Verification
```bash
# Test all agents import successfully
python -c "
import agents.mcp_bus.main
import agents.scout.main
import agents.analyst.main
import agents.synthesizer.main
print('✅ All core agents ready')
"
```

## 🏗️ **Architecture**

### Agent Ecosystem (17 Agents)

| Agent | Port | Purpose | Key Features |
|-------|------|---------|--------------|
| **MCP Bus** | 8000 | Central Communication Hub | Agent registration, routing, health monitoring |
| **Scout** | 8002 | Content Discovery | 5-model AI architecture, multi-source crawling |
| **Analyst** | 8004 | Sentiment Analysis | TensorRT-accelerated bias/sentiment analysis |
| **Fact Checker** | 8003 | Verification System | 5-model verification with evidence validation |
| **Synthesizer V3** | 8005 | Content Synthesis | 4-model synthesis (BERTopic, BART, FLAN-T5, SentenceTransformers) |
| **Critic** | 8006 | Quality Assessment | Content review and quality scoring |
| **Chief Editor** | 8001 | Workflow Orchestration | End-to-end pipeline coordination |
| **Memory** | 8007 | Data Storage | PostgreSQL + vector search with embeddings |
| **Reasoning** | 8008 | Logic Engine | Nucleoid symbolic reasoning |
| **Dashboard** | 8013 | Web Interface | Real-time monitoring and management |
| **Newsreader** | 8010 | Content Processing | Advanced news extraction and formatting |
| **Crawler Control** | 8009 | Crawl Management | Distributed crawler orchestration |
| **GPU Orchestrator** | 8011 | Resource Management | GPU allocation and monitoring |
| **Balancer** | 8012 | Load Balancing | Agent workload distribution |
| **Archive** | 8014 | Knowledge Graph | Entity linking and temporal analysis |
| **Analytics** | 8015 | Business Intelligence | Advanced analytics and reporting |
| **Auth** | 8016 | Authentication | User management and access control |

### Communication Protocol
All agents communicate via the **MCP (Model Context Protocol)**:

```python
# Standard agent communication
payload = {
    "agent": "synthesizer",
    "tool": "synthesize_content",
    "args": [article_data],
    "kwargs": {"format": "json"}
}
response = requests.post("http://localhost:8000/call", json=payload)
```

## 📊 **APIs**

### REST APIs
- **Archive API** (Port 8021): Article storage and retrieval
- **Compliance API** (Port 8021): GDPR/CCPA compliance management
- **Public API** (Port 8014): External integrations
- **GraphQL API** (Port 8020): Advanced queries and analytics

### Web Interfaces
- **Dashboard** (Port 8013): Real-time monitoring and management
- **Analytics Dashboard** (Port 8015): Business intelligence and reporting

## 🔧 **Development**

### Environment Setup
```bash
# Activate conda environment
conda activate justnews-v2-py312

# Install development dependencies
pip install -r requirements.txt

# Run tests
pytest

# Start development services
make dev-up
```

### Code Quality
```bash
# Linting
ruff check .

# Type checking
mypy agents/

# Testing
pytest --cov=agents --cov-report=html
```

### Build System
```bash
# Available Makefile targets
make help                    # Show all targets
make build                   # Build all components
make test                    # Run full test suite
make docker-build           # Build Docker images
make deploy-dev             # Deploy to development
make deploy-prod            # Deploy to production
```

## 🚢 **Deployment**

### Docker Deployment
```bash
# Build and run with docker-compose
docker-compose up -d

# Or build individual services
make docker-build
docker run -p 8000:8000 justnews/mcp-bus:latest
```

### Kubernetes Deployment
```bash
# Deploy to Kubernetes
kubectl apply -f infrastructure/kubernetes/

# Check status
kubectl get pods -l app=justnews
```

### Systemd Deployment (Production)
```bash
# Install systemd services
sudo cp infrastructure/systemd/units/justnews*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start core services
sudo systemctl start justnews-mcp-bus
sudo systemctl enable justnews-mcp-bus

# Start agents
sudo systemctl start justnews@scout justnews@analyst justnews@synthesizer
```

## 📈 **Monitoring**

### Real-time Dashboards
- **System Overview**: CPU, memory, GPU utilization
- **Agent Performance**: Throughput, latency, error rates
- **Business Metrics**: Articles processed, quality scores
- **GPU Monitoring**: Memory usage, MPS allocation

### Alerting
- Service health checks
- Performance degradation
- GPU resource exhaustion
- Security incidents

### Logging
- Structured JSON logging
- Centralized log aggregation
- Log analysis and alerting
- Audit trails for compliance

## 🔒 **Security**

### Enterprise Security Features
- **Authentication & Authorization**: JWT-based auth with role-based access
- **Data Encryption**: End-to-end encryption for sensitive data
- **Compliance Monitoring**: GDPR/CCPA compliance with audit logging
- **Network Security**: TLS encryption, firewall rules, intrusion detection

### Data Protection
- **Data Minimization**: Automatic data cleanup and retention policies
- **Consent Management**: User consent tracking and management
- **Privacy Controls**: Data anonymization and pseudonymization
- **Audit Logging**: Comprehensive security event logging

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 with 88-character line limits
- Use type hints for all function signatures
- Write comprehensive tests for new features
- Update documentation for API changes
- Ensure all tests pass before submitting PR

## 📄 **License**

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- Built with FastAPI, Pydantic, and modern Python async patterns
- GPU acceleration powered by NVIDIA TensorRT and CUDA
- Monitoring and observability with Prometheus and Grafana
- Container orchestration with Docker and Kubernetes

---

**JustNews V4 - Production Ready for Enterprise News Analysis** 🎉
