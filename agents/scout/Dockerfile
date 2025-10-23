
### DEPRECATED: Dockerfiles are deprecated for core deployments. Prefer native Ubuntu deployment. See markdown_docs/development_reports/DEPRECATE_DOCKER.md
FROM nvidia/cuda:12.1-devel-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3-pip \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create symlinks for python
RUN ln -s /usr/bin/python3.11 /usr/bin/python && \
    ln -s /usr/bin/python3.11 /usr/bin/python3

# Upgrade pip and install build tools
RUN python -m pip install --upgrade pip setuptools wheel

# Copy and install Python requirements
COPY agents/scout/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Scout agent files
COPY agents/scout/main.py .
COPY agents/scout/tools.py .
COPY agents/scout/gpu_scout_engine.py .

# Set environment variables for the Scout agent
ENV PYTHONPATH="/app"
ENV TRANSFORMERS_CACHE="/app/.cache/huggingface"
ENV HF_HOME="/app/.cache/huggingface"
ENV SCOUT_AGENT_PORT=8002
ENV CUDA_VISIBLE_DEVICES=0

# Create cache directory
RUN mkdir -p /app/.cache/huggingface

EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
