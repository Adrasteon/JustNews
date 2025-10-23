
### DEPRECATED: Dockerfiles are deprecated for core deployments. Prefer native Ubuntu deployment. See markdown_docs/development_reports/DEPRECATE_DOCKER.md
# Dockerfile for Fact-Checker Agent
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and Python build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install setuptools and wheel first to replace distutils
RUN pip install --upgrade pip setuptools wheel

COPY agents/fact_checker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create common directory structure
RUN mkdir -p agents/common

COPY agents/fact_checker/main.py .
COPY agents/fact_checker/tools.py .
COPY agents/fact_checker/gpu_tools.py .
COPY agents/common/gpu_manager.py ./agents/common/

ENV PYTHONPATH="/app"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
