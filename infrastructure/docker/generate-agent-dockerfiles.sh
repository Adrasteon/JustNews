#!/bin/bash
# Script to generate Dockerfiles for all JustNews agents

# Agent configurations: name:port
declare -A agents=(
    ["synthesizer"]="8005"
    ["fact-checker"]="8003"
    ["memory"]="8007"
    ["reasoning"]="8008"
    ["newsreader"]="8009"
    ["critic"]="8006"
    ["dashboard"]="8013"
    ["analytics"]="8011"
    ["archive"]="8012"
    ["balancer"]="8010"
    ["crawler"]="8014"
    ["gpu-orchestrator"]="8015"
)

# Create Dockerfiles for each agent
for agent in "${!agents[@]}"; do
    port=${agents[$agent]}

    cat > "infrastructure/docker/agent-dockerfiles/Dockerfile.${agent}" << EOF
# Dockerfile for ${agent} agent
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:\$PATH"

# Set working directory
WORKDIR /opt/justnews

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash justnews && \\
    chown -R justnews:justnews /opt/justnews

# Create necessary directories
RUN mkdir -p /var/log/justnews && \\
    chown -R justnews:justnews /var/log/justnews

# Switch to non-root user
USER justnews

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:${port}/health || exit 1

# Expose port
EXPOSE ${port}

# Start the ${agent} service
CMD ["python", "-m", "agents.${agent}.main"]
EOF

    echo "Generated Dockerfile for ${agent} (port ${port})"
done

echo "All agent Dockerfiles generated successfully!"