#!/bin/bash

# JustNews Docker Deployment Test Script
# This script validates that the Docker deployment is working correctly

set -e

COMPOSE_FILE="docker-compose.yml"
PROJECT_NAME="justnews"

echo "🧪 Testing JustNews Docker Deployment"
echo "====================================="

# Function to check if a service is healthy
check_service() {
    local service=$1
    local port=$2
    local max_attempts=30
    local attempt=1

    echo "⏳ Checking $service on port $port..."

    while [ $attempt -le $max_attempts ]; do
        if docker-compose ps $service | grep -q "Up"; then
            echo "✅ $service is running"
            return 0
        fi
        echo "   Attempt $attempt/$max_attempts: $service not ready yet..."
        sleep 2
        ((attempt++))
    done

    echo "❌ $service failed to start"
    return 1
}

# Function to test HTTP endpoint
test_endpoint() {
    local service=$1
    local port=$2
    local path=${3:-/health}
    local max_attempts=10
    local attempt=1

    echo "🌐 Testing $service endpoint: http://localhost:$port$path"

    while [ $attempt -le $max_attempts ]; do
        if curl -f -s "http://localhost:$port$path" > /dev/null 2>&1; then
            echo "✅ $service endpoint responding"
            return 0
        fi
        echo "   Attempt $attempt/$max_attempts: endpoint not responding..."
        sleep 3
        ((attempt++))
    done

    echo "❌ $service endpoint not responding"
    return 1
}

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install Docker Compose."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "📝 Please edit .env file with your configuration before running tests."
    echo "   For now, using default values..."
fi

echo "🐳 Starting Docker services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to start..."
sleep 10

# Test infrastructure services
echo ""
echo "🔧 Testing Infrastructure Services:"
check_service "postgres" "5432"
check_service "redis" "6379"
test_endpoint "mcp-bus" "8000"

# Test CPU-based agents
echo ""
echo "🤖 Testing CPU-based Agents:"
test_endpoint "scout" "8002"
test_endpoint "chief-editor" "8001"
test_endpoint "memory" "8007"
test_endpoint "reasoning" "8008"
test_endpoint "critic" "8006"
test_endpoint "dashboard" "8013"
test_endpoint "analytics" "8011"
test_endpoint "archive" "8012"
test_endpoint "balancer" "8010"
test_endpoint "gpu-orchestrator" "8015"

# Test GPU-based agents (if GPU available)
echo ""
echo "🎮 Testing GPU-based Agents:"
if docker system info | grep -q "nvidia"; then
    echo "✅ NVIDIA runtime detected, testing GPU agents..."
    test_endpoint "analyst" "8004"
    test_endpoint "synthesizer" "8005"
    test_endpoint "fact-checker" "8003"
    test_endpoint "newsreader" "8009"
else
    echo "⚠️  NVIDIA runtime not detected, GPU agents may not work properly"
    echo "   Testing anyway..."
    test_endpoint "analyst" "8004" || echo "   (Expected if no GPU)"
    test_endpoint "synthesizer" "8005" || echo "   (Expected if no GPU)"
    test_endpoint "fact-checker" "8003" || echo "   (Expected if no GPU)"
    test_endpoint "newsreader" "8009" || echo "   (Expected if no GPU)"
fi

# Test monitoring services
echo ""
echo "📊 Testing Monitoring Services:"
test_endpoint "prometheus" "9090" "/-/ready"
test_endpoint "grafana" "3000" "/api/health"

echo ""
echo "📋 Service Status Summary:"
docker-compose ps

echo ""
echo "🎉 Docker deployment test completed!"
echo ""
echo "Useful commands:"
echo "  View logs: docker-compose logs -f [service-name]"
echo "  Stop services: docker-compose down"
echo "  Restart service: docker-compose restart [service-name]"
echo ""
echo "Access points:"
echo "  Dashboard: http://localhost:8013"
echo "  Grafana: http://localhost:3000 (admin/admin)"
echo "  Prometheus: http://localhost:9090"
echo "  MCP Bus: http://localhost:8000"