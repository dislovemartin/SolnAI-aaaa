# SolnAI Container Setup

This document provides instructions for building and running the SolnAI/Chimera platform using Docker containers.

## Prerequisites

- Docker and Docker Compose installed
- NVIDIA Container Toolkit installed (for GPU support)
- NVIDIA GPU with CUDA support
- Git LFS (for large model files)
- NVIDIA API Key (for LLM Router and AgentIQ)

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/SolnAI.git
   cd SolnAI
   ```

2. Set your NVIDIA API Key as an environment variable:
   ```bash
   export NVIDIA_API_KEY=your-nvidia-api-key
   ```

   You can obtain a NVIDIA API Key from [NVIDIA API Catalog](https://build.nvidia.com/explore/discover).

3. Build and start the containers:
   ```bash
   docker-compose up -d
   ```

   This will build the SolnAI container using the NVIDIA Triton Server base image (`nvcr.io/nvidia/tritonserver-pb24h2:24.08.07-py3-min`) and start all required services.

4. Access the services:
   - Triton Server HTTP: http://localhost:8000
   - Triton Server metrics: http://localhost:8002
   - FastAPI services: http://localhost:8080
   - Neo4j browser: http://localhost:7474
   - NATS monitoring: http://localhost:8222
   - LLM Router: http://localhost:8084
   - AgentIQ UI: http://localhost:8100

## Container Structure

The SolnAI container is built on NVIDIA's Triton Server image and includes:

- NVIDIA Triton Inference Server for model serving
- Python with FastAPI for microservices
- Rust components for high-performance services
- GPU acceleration support (CUDA, PyTorch, FAISS-GPU)
- Integration with Redis, Neo4j, and NATS
- LLM Router for intelligent routing of prompts to appropriate LLMs
- AgentIQ for building and orchestrating AI agents with various tools

## LLM Router

The LLM Router is a framework that intelligently routes user prompts to the most appropriate LLM based on the task or complexity of the request. Key features include:

- **Task-based routing**: Routes prompts to specialized LLMs based on task classification
- **Complexity-based routing**: Routes prompts based on complexity assessment
- **OpenAI API compatible**: Works as a drop-in replacement for applications using OpenAI's API

To use the LLM Router:

1. Send requests to the router endpoint at `http://localhost:8084/v1/chat/completions`
2. Include routing metadata in your request:
   ```json
   {
     "model": "",
     "messages": [...],
     "nim-llm-router": {
       "policy": "task_router",
       "routing_strategy": "triton",
       "model": ""
     }
   }
   ```

## AgentIQ

AgentIQ is a flexible library for building and orchestrating AI agents with access to various tools and data sources. Key features include:

- **Framework-agnostic**: Works with any agentic framework
- **Reusable components**: Build agents, tools, and workflows that can be combined and repurposed
- **Profiling & Observability**: Track performance and identify bottlenecks
- **Evaluation**: Validate accuracy with built-in evaluation tools

To use AgentIQ:

1. Access the web UI at `http://localhost:8100`
2. Create workflow configurations in YAML format
3. Use the `aiq` CLI to run workflows programmatically

Example workflow file:
```yaml
functions:
  wikipedia_search:
    _type: wiki_search
    max_results: 2

llms:
  nim_llm:
    _type: nim
    model_name: meta/llama-3.1-70b-instruct
    temperature: 0.0

workflow:
  _type: react_agent
  tool_names: [wikipedia_search]
  llm_name: nim_llm
  verbose: true
```

## Configuration

Environment variables can be modified in the `docker-compose.yml` file:

- `NVIDIA_VISIBLE_DEVICES`: Control which GPUs are used
- `REDIS_URL`: Redis connection string
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`: Neo4j connection details
- `NATS_URL`: NATS connection string
- `NVIDIA_API_KEY`: API key for NVIDIA NIM models
- `LLM_ROUTER_PORT`: Port for the LLM Router service
- `AGENTIQ_PORT`: Port for the AgentIQ web interface
- `TRITON_SERVER_PORT`: Port for the Triton Inference Server

## Building Manually

If you need to build the container manually:

```bash
docker build -t solnai:latest -f Dockerfile .
```

## Running in Production

For production deployments:

1. Set secure passwords in the `docker-compose.yml` file
2. Configure volume persistence
3. Set up proper networking and firewall rules
4. Consider using Docker Swarm or Kubernetes for orchestration
5. Secure the NVIDIA API Key using environment variables or secrets management

## Troubleshooting

- **GPU not detected**: Ensure the NVIDIA Container Toolkit is properly installed and the `nvidia-smi` command works on the host
- **Connection issues**: Check that all required ports are exposed and not blocked by firewalls
- **Memory errors**: Adjust memory settings for Neo4j and other services in `docker-compose.yml`
- **LLM Router errors**: Verify your NVIDIA API Key is valid and set correctly
- **AgentIQ issues**: Check the logs with `docker logs solnai` and look for AgentIQ-related errors

## Models

Place your model files in the `models` directory. The Triton Server will automatically load models from this directory.

For LLM Router, the following models are recommended:
- `task_router_ensemble`: Routes prompts based on task classification
- `complexity_router_ensemble`: Routes prompts based on complexity assessment

## Advanced Usage

### Scaling

To scale the system horizontally, consider using Kubernetes with the provided Dockerfile. The container is designed to work with Kubernetes and the NVIDIA GPU Operator.

### Custom Models

To add custom models to Triton Server:

1. Create a model repository structure in the `models` directory
2. Follow the Triton Server model repository guidelines
3. Restart the container

### Custom Routing Policies

To create custom routing policies for the LLM Router:

1. Follow the instructions in the `/app/llm-router/customize/README.md` file
2. Update the router configuration in `/app/llm-router/src/router-controller/config.yml`

### Custom AgentIQ Workflows

To create custom AgentIQ workflows:

1. Create a new YAML configuration file
2. Define functions, LLMs, and workflow components
3. Run the workflow using the `aiq` CLI or the web UI

## License

Copyright © 2025 SolnAI 