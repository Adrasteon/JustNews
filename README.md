# JustNewsAgent V4.0.0

A production-ready multi-agent news analysis system featuring GPU-accelerated processing, continuous learning, and distributed architecture.

## 🚀 Quick Start

### Prerequisites
- Python 3.10+ (via conda environment)
- PostgreSQL 14+
- Docker & Docker Compose (optional)
- GPU with CUDA support (recommended)
- Miniconda or Anaconda installed

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd JustNewsAgent
```

2. Set up conda environment:
```bash
# Create conda environment (if not already created)
conda env create -f environment.yml

# Activate the environment
conda activate justnews-v2-py312
```

3. Install dependencies (prefer conda-forge for the crawler extraction stack):
```bash
mamba install -c conda-forge --file requirements.txt
# or, if mamba is unavailable
conda install -c conda-forge --file requirements.txt
```

4. Set up the database:
```bash
make setup-db
```

5. Start the system:
```bash
make start
```

## 📋 System Architecture

### Core Components
- **18 AI Agents**: Specialized agents for news analysis, fact-checking, synthesis
- **MCP Bus**: Model Context Protocol for inter-agent communication
- **Consumer Platform**: Website and APIs for end-user access
- **Training System**: Continuous learning with MCP integration
- **Monitoring**: Centralized logging, metrics, and distributed tracing

### Key Features
- **GPU Acceleration**: TensorRT-optimized models for performance
- **High-Precision Extraction**: Trafilatura-first crawler cascade with readability/jusText fallbacks, structured metadata, raw HTML archival, and quality heuristics
- **Enterprise Security**: JWT authentication, RBAC, GDPR compliance
- **Multi-Platform Deployment**: Docker, Kubernetes, systemd support
- **Comprehensive Testing**: 80%+ test coverage with integration tests
- **Production Monitoring**: Real-time dashboards and alerting

## 🛠️ Development

### Environment Setup
Before running any development commands, always activate the conda environment:
```bash
conda activate justnews-v2-py312
```

### Available Commands
```bash
make help          # Show all available commands
make test          # Run test suite with coverage
make lint          # Run code quality checks
make format        # Format code with consistent style
make clean         # Clean build artifacts and cache files
make build         # Build production artifacts
make deploy        # Deploy to target environment
make docs          # Generate and validate documentation
make ci-check      # Run CI validation checks
make release       # Create and publish release

Environment variables:
  ENV         Target environment (development/staging/production)
  VERSION     Release version (for release target)
  DOCKER_TAG  Docker image tag (for deploy target)
```

### Conda Environment Management
```bash
# Activate environment
conda activate justnews-v2-py312

# Deactivate environment
conda deactivate

# Update environment
conda env update -f environment.yml

# List installed packages
conda list

# Export environment (for backup)
conda env export > environment_backup.yml
```

### Crawler Extraction Regression Tests
```bash
PYTHONPATH=$(pwd) pytest tests/agents/crawler -q
```

This suite covers the Stage B2 extraction pipeline, including the Trafilatura/readability/jusText cascade, raw HTML persistence, and ingestion metadata enrichment.

### Project Structure
```
JustNewsAgent/
├── agents/           # 18 specialized AI agents
├── config/           # Unified configuration system
├── database/         # Advanced ORM with migrations
├── docs/             # Unified documentation platform
├── infrastructure/   # Multi-platform deployment
├── monitoring/       # Centralized observability
├── scripts/          # Organized script ecosystem
├── security/         # Enterprise security framework
├── tests/            # Comprehensive testing suite
├── training_system/  # MCP-integrated learning
├── public_website.html    # Consumer-facing website
└── requirements.txt       # Python dependencies
```

## 📚 Documentation

- [API Documentation](./docs/api/)
- [User Guides](./docs/user-guides/)
- [Operations Guide](./docs/operations/)
- [Developer Documentation](./docs/developer/)

## 🤝 Contributing

See [CONTRIBUTING.md](./docs/CONTRIBUTING.md) for development guidelines.

## 📄 License

See [LICENCE](./LICENCE) for licensing information.

## 🏆 Refactoring Status

✅ **ALL 11 MAJOR REFACTORING AREAS COMPLETE**
- Agent System: 18 standardized agents operational
- Consumer Platform: Website, APIs, authentication complete
- Configuration: Pydantic V2 unified system
- Database: Advanced ORM with connection pooling
- Monitoring: Centralized logging, metrics, tracing
- Security: Enterprise-grade auth and compliance
- Testing: Comprehensive framework with 80%+ coverage
- Build/CI: Unified automation with containerization
- Deployment: Multi-platform support (Docker/K8s/systemd)
- Documentation: Unified platform with latest patterns
- Training: MCP-integrated continuous learning

**Status**: Production-ready enterprise system
