# Dockerfile for Chief Editor Agent
### DEPRECATED: Dockerfiles are deprecated for core deployments. Prefer native Ubuntu deployment. See markdown_docs/development_reports/DEPRECATE_DOCKER.md
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and Python build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install setuptools and wheel first to replace distutils
RUN pip install --upgrade pip setuptools wheel

COPY agents/chief_editor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/chief_editor/main.py .
COPY agents/chief_editor/tools.py .

ENV PYTHONPATH="/app"

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
