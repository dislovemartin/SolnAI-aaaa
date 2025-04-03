#!/bin/bash
set -e

echo "Starting SolnAI container..."

# Function to check GPU status
check_gpu() {
  echo "Checking for GPU access..."
  
  # Check common NVIDIA paths and tools
  if [ -d "/usr/local/cuda" ]; then
    echo "CUDA directory found at /usr/local/cuda"
    ls -la /usr/local/cuda/bin/ | grep -E 'nvidia|cuda' || echo "No NVIDIA/CUDA binaries found"
  else
    echo "CUDA directory not found at /usr/local/cuda"
  fi
  
  # Check for NVIDIA devices
  if [ -e "/dev/nvidia0" ]; then
    echo "NVIDIA device found: /dev/nvidia0"
    ls -la /dev/nvidia* || echo "No additional NVIDIA devices"
  else
    echo "No NVIDIA devices found in /dev"
  fi
  
  # Try nvidia-smi
  if command -v nvidia-smi &> /dev/null; then
    echo "GPU Information:"
    nvidia-smi
    echo "GPU successfully detected and available."
    return 0
  else
    echo "WARNING: nvidia-smi not available or not accessible."
    # Check environment variables
    if [ -n "$NVIDIA_VISIBLE_DEVICES" ]; then
      echo "NVIDIA_VISIBLE_DEVICES is set to: $NVIDIA_VISIBLE_DEVICES"
    fi
    if [ -n "$CUDA_VISIBLE_DEVICES" ]; then
      echo "CUDA_VISIBLE_DEVICES is set to: $CUDA_VISIBLE_DEVICES"
    fi
    return 1
  fi
}

# Run GPU check
check_gpu || echo "Continuing with reduced performance (CPU only)"

# Print environment information
echo "Environment Variables:"
echo "NVIDIA_VISIBLE_DEVICES=${NVIDIA_VISIBLE_DEVICES}"
echo "NVIDIA_DRIVER_CAPABILITIES=${NVIDIA_DRIVER_CAPABILITIES}"
echo "LD_LIBRARY_PATH=${LD_LIBRARY_PATH}"
echo "PATH=${PATH}"
echo "PYTHONPATH=${PYTHONPATH}"

# Debug Python and venv
echo "Checking Python environment..."
echo "Python version: $(python3 --version)"
echo "Python executable: $(which python3)"
echo "AgentIQ venv Python: $(ls -la /app/AgentIQ/.venv/bin/python || echo 'Not found')"

# Test Python execution permission
if [ -f "/app/AgentIQ/.venv/bin/python" ]; then
  echo "Testing venv Python execution..."
  if /app/AgentIQ/.venv/bin/python -c "print('Python venv works')" 2>/dev/null; then
    echo "Python venv execution test: SUCCESS"
  else
    echo "Python venv execution test: FAILED - fixing permissions"
    chmod 755 /app/AgentIQ/.venv/bin/python
    chmod 755 /app/AgentIQ/.venv/bin/python3
  fi
else
  echo "ERROR: Python venv not found at expected path"
  exit 1
fi

# Check for external services
echo "Checking external services..."

# Redis check
if [ -n "${REDIS_URL}" ]; then
  echo "Using external Redis at ${REDIS_URL}"
else
  echo "No Redis URL provided. Some features may not work."
fi

# Neo4j check
if [ -n "${NEO4J_URI}" ]; then
  echo "Using external Neo4j at ${NEO4J_URI}"
else
  echo "No Neo4j URI provided. Some features may not work."
fi

# NATS check
if [ -n "${NATS_URL}" ]; then
  echo "Using external NATS at ${NATS_URL}"
else
  echo "Starting local NATS service..."
  if command -v nats-server &> /dev/null; then
    nohup nats-server &
    echo "NATS started in background."
    export NATS_URL=nats://localhost:4222
  else
    echo "NATS server not found. Some features may not work."
  fi
fi

# Check Triton server paths
if [ -d "/opt/tritonserver" ]; then
  echo "Triton server directory found"
  ls -la /opt/tritonserver/bin || echo "No binaries in /opt/tritonserver/bin"
else
  echo "Triton server directory not found. Models may not load correctly."
fi

# Define AgentIQ venv python path with absolute path
AGENTIQ_PYTHON="/app/AgentIQ/.venv/bin/python"

# Start router-server (Triton Server)
echo "Starting Triton Server for router models..."
cd /app/llm-router
if [ -d "/app/llm-router/routers" ]; then
  nohup tritonserver --log-verbose=1 --model-repository=/app/llm-router/routers &> /tmp/triton_server.log &
  TRITON_PID=$!
  echo "Triton Server started with PID: $TRITON_PID"
  sleep 5
  if ! ps -p $TRITON_PID > /dev/null; then
    echo "ERROR: Triton Server failed to start. Check logs:"
    cat /tmp/triton_server.log
    echo "Continuing without router models..."
  fi
else
  echo "WARNING: Router model repository not found at /app/llm-router/routers"
fi

# Start Router Controller
echo "Starting LLM Router Controller..."
cd /app/llm-router
if [ -f "/app/llm-router/src/router-controller/config.yml" ]; then
  # Check if binary exists
  if [ -f "/app/llm-router/target/release/router-controller" ]; then
    nohup /app/llm-router/target/release/router-controller &> /tmp/router_controller.log &
    CONTROLLER_PID=$!
    echo "Router Controller started with PID: $CONTROLLER_PID"
  else
    echo "ERROR: Router Controller binary not found, attempting to build..."
    cd /app/llm-router
    if command -v cargo &> /dev/null; then
      cargo build --release
      if [ -f "/app/llm-router/target/release/router-controller" ]; then
        nohup /app/llm-router/target/release/router-controller &> /tmp/router_controller.log &
        CONTROLLER_PID=$!
        echo "Router Controller built and started with PID: $CONTROLLER_PID"
      else
        echo "ERROR: Failed to build Router Controller"
      fi
    else
      echo "ERROR: Cargo not found, cannot build Router Controller"
    fi
  fi
else
  echo "WARNING: Router Controller config not found"
fi

# Start AgentIQ using its venv Python
echo "Starting AgentIQ service using $AGENTIQ_PYTHON ..."
cd /app/AgentIQ
$AGENTIQ_PYTHON -m examples.simple.app &> /tmp/agentiq_startup.log &
AGENTIQ_PID=$!
echo "AgentIQ started with PID: $AGENTIQ_PID"

# Make sure the process started successfully
sleep 3
if ps -p $AGENTIQ_PID > /dev/null; then
  echo "AgentIQ successfully started."
  # Move startup log to a persistent location
  mv /tmp/agentiq_startup.log /tmp/agentiq.log
else
  echo "ERROR: AgentIQ failed to start. Check logs:"
  cat /tmp/agentiq_startup.log
  echo "Attempting to run with debug mode:"
  PYTHONPATH="/app:/app/llm-router:/app/AgentIQ" $AGENTIQ_PYTHON -m examples.simple.app
  exit 1
fi

echo "All services started. Container is running."

# Create a function to display service status
show_status() {
  echo "====== SolnAI Status $(date) ======"
  echo "Checking service status:"
  
  # Check Triton Server
  if pgrep -f "tritonserver" > /dev/null; then
    echo "✅ Triton Server running"
  else
    echo "❌ Triton Server not running"
    tail -10 /tmp/triton_server.log || echo "No log file found"
  fi
  
  # Check Router Controller
  if pgrep -f "router-controller" > /dev/null; then
    echo "✅ Router Controller running"
  else
    echo "❌ Router Controller not running"
    tail -10 /tmp/router_controller.log || echo "No log file found"
  fi
  
  # Check AgentIQ
  if pgrep -f "examples.simple.app" > /dev/null; then
    echo "✅ AgentIQ running"
  else
    echo "❌ AgentIQ not running"
    tail -10 /tmp/agentiq.log || echo "No log file found"
  fi
  
  # Check endpoints
  curl -s -o /dev/null -w "Router Controller Healthcheck: %{http_code}\n" http://localhost:8084/health 2>/dev/null || echo "Router Controller endpoint not responding"
  curl -s -o /dev/null -w "AgentIQ UI: %{http_code}\n" http://localhost:8100 2>/dev/null || echo "AgentIQ UI not responding"

  echo "==============================="
}

# Keep container running with status checks
while true; do
  show_status
  sleep 60
done 