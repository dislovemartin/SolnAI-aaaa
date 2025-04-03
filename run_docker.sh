#!/bin/bash
set -e

echo "=== SolnAI Container Build and Run Script ==="
echo "This script will build and run the SolnAI container with GPU support"

# Check for GPU and NVIDIA container toolkit
echo "Checking prerequisites..."
if ! command -v nvidia-smi &> /dev/null; then
    echo "ERROR: nvidia-smi not found. Ensure NVIDIA drivers are installed."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not found. Please install Docker."
    exit 1
fi

# Check for nvidia-container-toolkit 
echo "Checking for NVIDIA Container Toolkit..."
if ! grep -q 'nvidia' <<< "$(docker info 2>/dev/null | grep 'Runtimes')"; then
    echo "WARNING: NVIDIA Docker runtime not detected. GPU support may not work."
    echo "You may need to install nvidia-container-toolkit and restart Docker."
    echo "Continue anyway? (y/n)"
    read -r answer
    if [[ "$answer" != "y" ]]; then
        exit 1
    fi
fi

# Download router models if they don't exist
echo "Checking for router models..."
if [ ! -d "llm-router/routers" ]; then
    echo "Router models directory not found. Would you like to set it up? (y/n)"
    read -r answer
    if [[ "$answer" == "y" ]]; then
        echo "Setting up router models directory..."
        mkdir -p llm-router/routers
    fi
fi

# Build the container
echo "Building the SolnAI container..."
docker build -t solnai:24.08.07 .

# Check if build was successful
if [ $? -ne 0 ]; then
    echo "ERROR: Docker build failed."
    exit 1
fi

# Setup config.yml if needed
if [ ! -f "llm-router/src/router-controller/config.yml" ]; then
    echo "Router controller config not found, copying template..."
    cp llm-router/src/router-controller/config.yaml llm-router/src/router-controller/config.yml
    
    # Ask for NVIDIA API key
    echo "Please enter your NVIDIA API key for the router config:"
    read -r nvidia_api_key
    
    # Update config.yml with the API key
    if [ -n "$nvidia_api_key" ]; then
        sed -i "s/api_key: /api_key: $nvidia_api_key/g" llm-router/src/router-controller/config.yml
        echo "API key added to config.yml"
    else
        echo "WARNING: No API key provided. Router may not work correctly."
    fi
fi

# Run as a standalone container without docker-compose
echo "Running the SolnAI container with GPU support..."
docker run --rm -it \
    --name solnai \
    --hostname solnai \
    --gpus all \
    -e NVIDIA_VISIBLE_DEVICES=all \
    -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    -e PYTHONUNBUFFERED=1 \
    -e PYTHONPATH=/app:/app/llm-router:/app/AgentIQ \
    -e NVIDIA_API_KEY="$nvidia_api_key" \
    -e LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64 \
    -p 8000:8000 \
    -p 8001:8001 \
    -p 8002:8002 \
    -p 8080:8080 \
    -p 9090:9090 \
    -p 8084:8084 \
    -p 8100:8100 \
    -v $(pwd)/scripts:/app/scripts:ro \
    -v $(pwd)/models:/app/models:cached \
    -v $(pwd)/llm-router/routers:/app/llm-router/routers:cached \
    -v $(pwd)/llm-router/src/router-controller/config.yml:/app/llm-router/src/router-controller/config.yml \
    solnai:24.08.07

echo "Container exited." 