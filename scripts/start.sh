#!/bin/bash
set -e

# Initialize environment variables from .env or use defaults
export NVIDIA_API_KEY=${NVIDIA_API_KEY:-""}
export TRITON_SERVER_PORT=${TRITON_SERVER_PORT:-8000}
export LLM_ROUTER_PORT=${LLM_ROUTER_PORT:-8084}
export AGENTIQ_PORT=${AGENTIQ_PORT:-8100}
export REDIS_PASSWORD=${REDIS_PASSWORD:-""}
export GPU_MEMORY_FRACTION=${GPU_MEMORY_FRACTION:-0.9}

echo "Starting SolnAI container services..."

# Path to Triton configuration file
TRITON_CONFIG="/app/infrastructure/triton/triton.conf"
MODELS_DIR="/app/models"

# Initialize the models directory for Triton Server
echo "Initializing Triton Server models..."
if [ -f "/app/scripts/init_models.sh" ]; then
  /app/scripts/init_models.sh
else
  echo "Model initialization script not found. Please check your installation."
fi

# Make sure the models directory exists
if [ ! -d "${MODELS_DIR}" ]; then
  echo "ERROR: Models directory not found or initialization failed."
  exit 1
fi

# Function to wait for a service to be ready
wait_for_service() {
  local host=$1
  local port=$2
  local service=$3
  local retries=${4:-30}
  local wait_time=${5:-2}
  
  echo "Waiting for $service to be ready at $host:$port..."
  
  for i in $(seq 1 $retries); do
    if nc -z "$host" "$port"; then
      echo "$service is ready!"
      return 0
    fi
    
    echo "Waiting for $service... ($i/$retries)"
    sleep $wait_time
  done
  
  echo "Error: $service did not start in time."
  return 1
}

# Install netcat if not already installed
if ! command -v nc &> /dev/null; then
  echo "Installing netcat..."
  apt-get update && apt-get install -y netcat-openbsd
fi

# Configure GPU memory fraction for TensorRT
if [ -n "$GPU_MEMORY_FRACTION" ]; then
  echo "Setting GPU memory fraction to ${GPU_MEMORY_FRACTION}"
  export TF_FORCE_GPU_ALLOW_GROWTH=true
  export TF_GPU_ALLOCATOR=cuda_malloc_async
fi

# Start the Triton Inference Server in the background
echo "Starting Triton Inference Server..."
if [ -f "$TRITON_CONFIG" ]; then
  echo "Using custom Triton configuration from $TRITON_CONFIG"
  # Parse config file line by line to remove comments and empty lines
  CONFIG_ARGS=$(grep -v "^#" "$TRITON_CONFIG" | grep -v "^[[:space:]]*$" | tr '\n' ' ')
  tritonserver $CONFIG_ARGS &
else
  echo "Using default Triton configuration"
  tritonserver --model-repository=${MODELS_DIR} --http-port=${TRITON_SERVER_PORT} &
fi
TRITON_PID=$!

# Wait for Triton to be ready
wait_for_service localhost ${TRITON_SERVER_PORT} "Triton Inference Server" 45 3

# Start the LLM Router
echo "Starting LLM Router..."
cd /app/llm-router
python -m src.test_router --port ${LLM_ROUTER_PORT} &
LLM_ROUTER_PID=$!

# Wait for the router to be ready
wait_for_service localhost ${LLM_ROUTER_PORT} "LLM Router" 30 2

# Start the SolnAI ML Orchestrator
echo "Starting SolnAI ML Orchestrator..."
cd /app
python -m microservices.python.ml-orchestrator.main &
ML_ORCHESTRATOR_PID=$!

# Start AgentIQ server
echo "Starting AgentIQ Server..."
cd /app/AgentIQ
source .venv/bin/activate
# Configure optimal thread settings for Python
export PYTHONTHREADDEBUG=0
export NUMEXPR_MAX_THREADS=$(nproc)
aiq ui start --host 0.0.0.0 --port ${AGENTIQ_PORT} &
AGENTIQ_PID=$!

# Wait for AgentIQ to be ready
wait_for_service localhost ${AGENTIQ_PORT} "AgentIQ" 40 3

echo "All services started successfully!"
echo "- Triton Server: http://localhost:${TRITON_SERVER_PORT}"
echo "- LLM Router: http://localhost:${LLM_ROUTER_PORT}"
echo "- AgentIQ: http://localhost:${AGENTIQ_PORT}"

# Start periodic health check
(
  while true; do
    # Check if services are still running
    if ! kill -0 $TRITON_PID 2>/dev/null; then
      echo "WARNING: Triton Server process died. Restarting..."
      tritonserver --model-repository=${MODELS_DIR} --http-port=${TRITON_SERVER_PORT} &
      TRITON_PID=$!
      sleep 5
    fi
    
    if ! kill -0 $LLM_ROUTER_PID 2>/dev/null; then
      echo "WARNING: LLM Router process died. Restarting..."
      cd /app/llm-router
      python -m src.test_router --port ${LLM_ROUTER_PORT} &
      LLM_ROUTER_PID=$!
      sleep 2
    fi
    
    if ! kill -0 $AGENTIQ_PID 2>/dev/null; then
      echo "WARNING: AgentIQ process died. Restarting..."
      cd /app/AgentIQ
      source .venv/bin/activate
      aiq ui start --host 0.0.0.0 --port ${AGENTIQ_PORT} &
      AGENTIQ_PID=$!
      sleep 3
    fi
    
    sleep 30
  done
) &
HEALTHCHECK_PID=$!

# Handle graceful shutdown
shutdown() {
  echo "Shutting down services..."
  
  # Kill healthcheck
  if [ -n "$HEALTHCHECK_PID" ]; then
    kill -TERM $HEALTHCHECK_PID 2>/dev/null || true
  }
  
  if [ -n "$AGENTIQ_PID" ]; then
    echo "Stopping AgentIQ..."
    kill -TERM $AGENTIQ_PID 2>/dev/null || true
    # Wait a bit for graceful shutdown
    sleep 2
  fi
  
  if [ -n "$ML_ORCHESTRATOR_PID" ]; then
    echo "Stopping ML Orchestrator..."
    kill -TERM $ML_ORCHESTRATOR_PID 2>/dev/null || true
    sleep 1
  fi
  
  if [ -n "$LLM_ROUTER_PID" ]; then
    echo "Stopping LLM Router..."
    kill -TERM $LLM_ROUTER_PID 2>/dev/null || true
    sleep 2
  fi
  
  if [ -n "$TRITON_PID" ]; then
    echo "Stopping Triton Server..."
    kill -TERM $TRITON_PID 2>/dev/null || true
    # Wait a bit longer for Triton to shut down gracefully
    sleep 3
  fi
  
  echo "Shutdown complete"
  exit 0
}

trap shutdown SIGTERM SIGINT

# Keep the script running to maintain the container
wait 