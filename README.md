# JustNews V4.0.0

A production-ready multi-agent news analysis system featuring GPU-accelerated processing, continuous learning, and distributed architecture.

## 🚀 Quick Start

### Prerequisites
- Python 3.10+ (via conda environment)
- MariaDB 10.11+ and ChromaDB (for vector operations)
- systemd (Docker Compose and Kubernetes deprecated)
- GPU with CUDA support (recommended)
- Miniconda or Anaconda installed

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd JustNews
```

2. Set up conda environment:
```bash
# Create conda environment (if not already created)
conda env create -f environment.yml

# Activate the environment
conda activate justnews-v2-py312-fix
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
- **Multi-Platform Deployment**: systemd (Kubernetes and Docker Compose deprecated)
- **Comprehensive Testing**: 41% test coverage with pytest-cov, comprehensive unit tests for utilities, agents, integration, operations, monitoring, and configuration
- **Production Monitoring**: Real-time dashboards and alerting
- **Advanced Crawler Resilience**: Modal handling, paywall detection, user-agent rotation, proxy pools, and stealth headers for robust web scraping

## 🛠️ Development

### Environment Setup
Before running any development commands, always activate the conda environment:
```bash
conda activate justnews-v2-py312-fix
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
  # DOCKER_TAG is deprecated and ignored. Use systemd package versioning instead.
```

### Conda Environment Management
```bash
# Activate environment
conda activate justnews-v2-py312-fix
Note: the canonical project conda environment is `justnews-v2-py312-fix`. When running scripts from documentation or CI, prefer:

```bash
# Run via conda-run
conda run -n justnews-v2-py312-fix python scripts/your_script.py

# Or use PYTHON_BIN to force a known interpreter
PYTHON_BIN=/home/adra/miniconda3/envs/justnews-v2-py312-fix/bin/python python scripts/your_script.py
```

This ensures scripts are executed with the same environment and binary used by deployment & startup helpers.

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
Prefer running tests using the project's conda environment to ensure third-party compiled extensions and dependencies are available.
```bash
# Either set `PYTHONPATH` and run pytest using the activated conda env:
PYTHONPATH=$(pwd) conda run -n justnews-v2-py312-fix pytest tests/agents/crawler -q

# Or set the `PYTHON_BIN` environment variable to the conda python executable:
PYTHONPATH=$(pwd) PYTHON_BIN=/home/adra/miniconda3/envs/justnews-v2-py312-fix/bin/python pytest tests/agents/crawler -q
```

This suite covers the Stage B2 extraction pipeline, including the Trafilatura/readability/jusText cascade, raw HTML persistence, and ingestion metadata enrichment.

### Project Structure
```
JustNews/
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
 - [Systemd (Native) Operations](/infrastructure/systemd/README.md)
- [Developer Documentation](./docs/developer/)

## 🤝 Contributing

See [CONTRIBUTING.md](./docs/CONTRIBUTING.md) for development guidelines.

Repository assistant guidance: See the canonical policy for automated helpers at `docs/copilot_instructions.md`. Developers may keep a local untracked file `.copilot-instructions` (listed in `.gitignore`) for personal overrides or machine-specific rules.

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
- Deployment: systemd (Kubernetes and Docker Compose deprecated)
- Documentation: Unified platform with latest patterns
- Training: MCP-integrated continuous learning

**Status**: Production-ready enterprise system

## ChromaDB Canonical Configuration (Operators)

This repository relies on a single canonical ChromaDB instance for vector storage and semantic operations. The system will validate that configured runtime Chroma host/port matches canonical settings when `CHROMADB_REQUIRE_CANONICAL=1` is set.

Set the required environment variables in `/etc/justnews/global.env` or your deployment environment. For example:

```dotenv
CHROMADB_HOST=localhost
CHROMADB_PORT=3307
CHROMADB_COLLECTION=articles
CHROMADB_REQUIRE_CANONICAL=1
CHROMADB_CANONICAL_HOST=localhost
CHROMADB_CANONICAL_PORT=3307
```

Operational commands to inspect and bootstrap Chroma: run the diagnostic and bootstrap helpers.
```bash
PYTHONPATH=. conda run -n justnews-v2-py312-fix python scripts/chroma_diagnose.py --host <host> --port <port> --autocreate
PYTHONPATH=. conda run -n justnews-v2-py312-fix python scripts/chroma_bootstrap.py --host <host> --port <port> --tenant default_tenant --collection articles
```

See `docs/chroma_setup.md` for advanced guidance and troubleshooting.
