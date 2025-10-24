#!/bin/bash

# Script to generate Dockerfiles for all JustNews agents
# Usage: ./generate_agent_dockerfiles.sh

set -e

# Agent configurations: name:port:gpu_required
AGENTS=(
    "scout:8002:false"
    "analyst:8004:true"
    "synthesizer:8005:true"
    "factChecker:8003:true"
    "memory:8007:false"
    "chiefEditor:8001:false"
    "reasoning:8008:false"
    "newsreader:8009:true"
    "critic:8006:false"
    "dashboard:8013:false"
    "analytics:8011:false"
    "archive:8012:false"
    "balancer:8010:false"
    "mcpBus:8000:false"
    "gpuOrchestrator:8015:false"
)

DOCKERFILE_DIR="infrastructure/docker/agent-dockerfiles"

# Create directory if it doesn't exist
mkdir -p "$DOCKERFILE_DIR"

for agent_config in "${AGENTS[@]}"; do
    IFS=':' read -r name port gpu_required <<< "$agent_config"

    if [ "$gpu_required" = "true" ]; then
        base_image="nvidia/cuda:12.1-base-ubuntu22.04"
        python_setup='
# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-dev \
    python3-pip \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create symbolic links for python
RUN ln -s /usr/bin/python3.12 /usr/bin/python3 && \
    ln -s /usr/bin/python3 /usr/bin/python'
        ml_deps='
# Install GPU-enabled ML dependencies
RUN pip install --no-cache-dir \
    torch==2.4.1 \
    torchvision==0.19.1 \
    torchaudio==2.4.1 \
    transformers==4.56.0 \
    tokenizers==0.22.0 \
    accelerate==1.10.1 \
    sentence-transformers==2.2.2 \
    safetensors==0.4.3 \
    bitsandbytes==0.47.0 \
    nvidia-ml-py3==7.352.0 \
    numpy>=1.24.0 \
    scipy>=1.11.0 \
    scikit-learn>=1.3.0 \
    pandas>=2.0.0 \
    networkx>=3.0 \
    spacy>=3.7.0'
        env_vars='DEBIAN_FRONTEND=noninteractive'
    else
        base_image="python:3.12-slim"
        python_setup='
# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*'
        ml_deps='
# Install ML dependencies
RUN pip install --no-cache-dir \
    torch==2.4.1 \
    torchvision==0.19.1 \
    transformers==4.56.0 \
    tokenizers==0.22.0 \
    accelerate==1.10.1 \
    sentence-transformers==2.2.2 \
    safetensors==0.4.3 \
    numpy>=1.24.0 \
    scipy>=1.11.0 \
    scikit-learn>=1.3.0 \
    pandas>=2.0.0 \
    networkx>=3.0 \
    spacy>=3.7.0'
        env_vars=""
    fi

    # Special handling for mcpBus (it's in mcp_bus directory)
    if [ "$name" = "mcpBus" ]; then
        agent_dir="mcp_bus"
    else
        agent_dir="$name"
    fi

    cat > "$DOCKERFILE_DIR/Dockerfile.$name" << EOF
# $name Agent Dockerfile$( [ "$gpu_required" = "true" ] && echo " (GPU-enabled)" )
FROM $base_image

# Set environment variables
ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PIP_NO_CACHE_DIR=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1 \\
    ${env_vars:+$env_vars \\}
    AGENT_NAME=$name \\
    AGENT_PORT=$port

$python_setup

# Set work directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
COPY environment.yml .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

$ml_deps

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# Copy common modules first
COPY common/ ./common/

# Copy agent-specific code
COPY agents/$agent_dir/ ./agents/$agent_dir/
COPY agents/__init__.py ./agents/

# Create main.py symlink for the $name agent
RUN ln -s agents/$agent_dir/main.py main.py

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \\
    && chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:$port/health || exit 1

# Expose port
EXPOSE $port

# Run the agent
CMD ["python", "main.py"]
EOF

    echo "Generated Dockerfile for $name agent (GPU: $gpu_required)"
done

echo "All agent Dockerfiles generated successfully!"