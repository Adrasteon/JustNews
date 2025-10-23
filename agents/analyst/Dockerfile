
### DEPRECATED: Dockerfiles are deprecated for core deployments. Prefer native Ubuntu deployment. See markdown_docs/development_reports/DEPRECATE_DOCKER.md
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and Python build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install setuptools and wheel first to replace distutils
RUN pip install --upgrade pip setuptools wheel

COPY agents/analyst/requirements_analyst.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install additional GPU dependencies
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
RUN pip install --no-cache-dir transformers accelerate safetensors sentencepiece protobuf

COPY agents/analyst/main.py .
COPY agents/analyst/tools.py .

ENV PYTHONPATH="/app"

EXPOSE 8004
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
