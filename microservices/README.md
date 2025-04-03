# SolnAI Microservices

This directory contains the microservices that power the SolnAI platform, built using Python and Rust.

## Architecture Overview

SolnAI's microservices architecture consists of specialized services that work together to provide an end-to-end AI solution. The system includes data ingestion, processing, storage, and retrieval capabilities with a focus on AI/ML operations.

```
┌─────────────────┐     ┌────────────────┐     ┌────────────────────┐
│                 │     │                │     │                    │
│ Ingestion       │────>│ ML             │────>│ Knowledge Graph    │
│ Service (Rust)  │     │ Orchestrator   │     │ Service (Python)   │
│                 │     │ (Python)       │     │                    │
└─────────────────┘     └────────────────┘     └────────────────────┘
                                │                        │
                                │                        │
                                ▼                        ▼
                        ┌────────────────┐     ┌────────────────────┐
                        │                │     │                    │
                        │ GPU Monitoring │     │ Personalization    │
                        │ Agent (Python) │     │ Engine (Python)    │
                        │                │     │                    │
                        └────────────────┘     └────────────────────┘
```

## Microservices

### Python Microservices

#### GPU Monitoring Agent

**Purpose**: Monitors NVIDIA GPU metrics and exposes them for Prometheus scraping.

**Features**:
- Collects GPU utilization, memory usage, temperature, and power metrics
- Exposes metrics via a Prometheus-compatible endpoint
- Auto-discovers available GPUs via NVML
- Includes health check endpoint

**Endpoints**:
- `/metrics`: Prometheus metrics endpoint
- `/health`: Health check endpoint

**Tech Stack**:
- Flask for HTTP server
- NVIDIA Management Library (NVML) via pynvml
- Prometheus client for metrics

#### Knowledge Graph Service

**Purpose**: Manages a knowledge graph using Neo4j to store entities and relationships extracted from content.

**Features**:
- Entity and relationship management
- Graph querying capabilities
- Integration with NLP enrichment pipeline
- Batch operations for entities and relationships

**Components**:
- Neo4j client for database operations
- NATS client for message processing
- Entity and relationship modeling

**Endpoints**:
- `/health`: Health check endpoint
- `/entities`: Entity creation endpoint
- `/relationships`: Relationship creation endpoint
- `/query`: Graph query endpoint
- `/entities/batch`: Batch entity operations

**Tech Stack**:
- FastAPI for HTTP server
- Neo4j for graph database
- NATS for messaging

#### ML Orchestrator

**Purpose**: Orchestrates NLP processing tasks using Triton Inference Server.

**Features**:
- Text summarization
- Entity extraction
- Background message processing
- Integration with NATS message streams

**Components**:
- Triton client for model inference
- NATS client for message processing
- Checkpoint management for model versions

**Endpoints**:
- `/health`: Health check endpoint
- `/process`: General processing endpoint
- `/summarize`: Text summarization endpoint
- `/extract_entities`: Entity extraction endpoint

**Tech Stack**:
- FastAPI for HTTP server
- NVIDIA Triton Inference Server client
- NATS for messaging

#### Personalization Engine

**Purpose**: Manages user profiles and content recommendations using vector embeddings.

**Features**:
- User profile management
- Content vectorization
- Personalized content recommendations
- Semantic search capabilities

**Components**:
- Vector store for embedding storage and retrieval
- NATS client for processing enriched content
- User profile and content modeling

**Endpoints**:
- `/health`: Health check endpoint
- `/users`: User profile management endpoints
- `/recommendations`: Content recommendation endpoint
- `/search`: Semantic search endpoint
- `/vectorize`: Content vectorization endpoint

**Tech Stack**:
- FastAPI for HTTP server
- Redis for vector database
- NATS for messaging

### Rust Microservices

#### Ingestion Service

**Purpose**: High-performance service for ingesting data from various sources.

**Features**:
- Fast data ingestion with Rust
- Validation and preprocessing of incoming data
- Publication to NATS streams for further processing
- Batch ingestion support

**Components**:
- Axum web framework for API endpoints
- NATS client for message publishing
- Error handling and validation

**Endpoints**:
- `/health`: Health check endpoint
- `/ingest`: Single item ingestion endpoint
- `/ingest/batch`: Batch ingestion endpoint

**Tech Stack**:
- Axum for HTTP server
- async-nats for NATS client
- Tokio for async runtime

## Communication

The microservices communicate primarily through NATS (a high-performance messaging system):

1. **Data Flow**:
   - Ingestion Service → ML Orchestrator → Knowledge Graph/Personalization Engine
   - Messages follow subjects like `ingest.validated.*`, `nlp.enriched.*`

2. **Message Formats**:
   - JSON-based messages with standardized fields
   - Includes metadata, payload, and processing results

## Deployment

All services are containerized using Docker and can be deployed in Kubernetes:

- Services include health checks for monitoring
- Configuration via environment variables
- Resource-specific containers (e.g., GPU monitoring agent requires NVIDIA runtime)

Docker Compose and Kubernetes manifests are provided for deployment.

## System Requirements

- Python 3.9+ for Python microservices
- Rust 2021 edition for Rust microservices
- NATS server for messaging
- Neo4j database for knowledge graph
- Redis for vector storage
- NVIDIA GPUs with appropriate drivers for ML workloads

## Development Guide

### Environment Setup

Each service has its own dependencies and environment requirements. Please refer to the respective service directories for specific setup instructions.

### Building and Running Services

#### Python Services

1. Navigate to the service directory
2. Install dependencies: `pip install -r requirements.txt`
3. Run the service: `python -m app.main` or using the provided Dockerfile

#### Rust Services

1. Navigate to the service directory
2. Build the service: `cargo build --release`
3. Run the service: `cargo run --release` or using the provided Dockerfile

## Configuration

Each service is configurable via environment variables, with sensible defaults provided in many cases. The configuration parameters are defined in respective config files (e.g., `config.py` or `config.rs`).

## Security Considerations

- Services use authentication for external systems (Neo4j, NATS)
- CORS is configured for API endpoints
- No direct exposure of internal services is recommended

## Monitoring & Observability

- Prometheus metrics exposed by GPU monitoring agent
- Health check endpoints for all services
- Logging with configurable levels
- Background health check loops in critical services 