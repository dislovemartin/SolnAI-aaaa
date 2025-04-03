#!/bin/bash
set -e

echo "SolnAI Container Runner"
echo "----------------------"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "Docker daemon is not running. Please start Docker first."
  exit 1
fi

# Check if NVIDIA runtime is available
if ! docker info | grep -q "nvidia"; then
  echo "WARNING: NVIDIA runtime not detected in Docker. GPU support may not work."
  echo "You might need to install nvidia-container-toolkit and configure Docker."
fi

# Check if NVIDIA GPU is available
if ! command -v nvidia-smi &> /dev/null; then
  echo "WARNING: nvidia-smi not found. GPU may not be available on this system."
else
  echo "GPU detected:"
  nvidia-smi | head -7
fi

# Create necessary directories if they don't exist
mkdir -p ./models

# Stop any existing container
echo "Stopping any existing SolnAI container..."
docker stop solnai 2>/dev/null || true
docker rm solnai 2>/dev/null || true

# Run other supporting services if they're not already running
echo "Checking and starting supporting services..."

# Check if redis is running, if not start it
if ! docker ps | grep -q solnai-redis; then
  echo "Starting Redis..."
  docker run -d --name solnai-redis \
    -p 6379:6379 \
    --restart unless-stopped \
    -v redis-data:/data \
    redis:7.2-alpine
fi

# Check if neo4j is running, if not start it
if ! docker ps | grep -q solnai-neo4j; then
  echo "Starting Neo4j..."
  docker run -d --name solnai-neo4j \
    -p 7474:7474 -p 7687:7687 \
    --restart unless-stopped \
    -v neo4j-data:/data \
    -v neo4j-logs:/logs \
    -e NEO4J_AUTH=neo4j/password \
    -e NEO4J_ACCEPT_LICENSE_AGREEMENT=yes \
    neo4j:5.15-enterprise
fi

# Check if nats is running, if not start it
if ! docker ps | grep -q solnai-nats; then
  echo "Starting NATS..."
  docker run -d --name solnai-nats \
    -p 4222:4222 \
    --restart unless-stopped \
    nats:2.10-alpine
fi

# Run the SolnAI container with GPU support
echo "Starting SolnAI container..."
docker run -d --name solnai \
  --runtime=nvidia \
  -p 8000:8000 -p 8001:8001 -p 8002:8002 \
  -p 8080:8080 -p 9090:9090 \
  -p 8084:8084 -p 8100:8100 \
  -v $(pwd)/scripts:/app/scripts \
  -v $(pwd)/models:/app/models:cached \
  -v nim-cache:/opt/nim/.cache \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  -e REDIS_URL=redis://$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' solnai-redis):6379/0 \
  -e NEO4J_URI=bolt://$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' solnai-neo4j):7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=password \
  -e NATS_URL=nats://$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' solnai-nats):4222 \
  -e LLM_ROUTER_PORT=8084 \
  -e AGENTIQ_PORT=8100 \
  -e TRITON_SERVER_PORT=8000 \
  solnai:24.08.07

# Check if the container started successfully
if [ $? -eq 0 ]; then
  echo "SolnAI container started successfully!"
  echo "Container logs:"
  docker logs solnai --tail 20
  
  echo ""
  echo "Services should be available at:"
  echo "- LLM Router: http://localhost:8084"
  echo "- AgentIQ UI: http://localhost:8100"
  echo "- Triton Server: http://localhost:8000"
  echo ""
  echo "To check container logs: docker logs solnai"
  echo "To stop the container: docker stop solnai"
else
  echo "Failed to start SolnAI container. Check the error messages above."
fi 