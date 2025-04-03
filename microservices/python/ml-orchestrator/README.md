# ML Orchestrator Service

A microservice for orchestrating NLP processing tasks using NVIDIA Triton Inference Server, handling the coordination of machine learning workflows.

## Features

- Automated processing of content through NLP pipelines
- Text summarization using state-of-the-art models
- Entity extraction for knowledge graph population
- Asynchronous processing via NATS message queues
- Integration with Triton Inference Server for scalable model serving
- Checkpoint management for model versioning
- Health monitoring and automatic reconnection

## Components

- **Triton Client**: Interface to Triton Inference Server
- **NATS Client**: Handles message streaming for async processing
- **Checkpoint Manager**: Manages model versions and deployments
- **FastAPI Server**: Provides REST API endpoints

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check endpoint |
| `/process` | POST | Process text through the NLP pipeline |
| `/summarize` | POST | Generate a summary for input text |
| `/extract_entities` | POST | Extract entities from input text |
| `/models` | GET | List available models |
| `/models/{model_name}/versions` | GET | List versions for a specific model |

## Message Processing

The service subscribes to the `ingest.validated.*` NATS subject to automatically process validated content:

1. Receives validated content from the ingestion service
2. Performs text extraction based on content type
3. Runs summarization and entity extraction on the text
4. Publishes enriched data to `nlp.enriched.*` subjects
5. Handles retries and error cases automatically

## Models

The service works with the following model types deployed on Triton:

- **Summarization Models**: Generate concise summaries of text content
- **Entity Extraction Models**: Identify and classify named entities
- **Embedding Models**: Generate vector embeddings for semantic search

## Requirements

- Python 3.8+
- NVIDIA Triton Inference Server 22.0+
- NATS Server 2.2+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

The service is configured using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `TRITON_URL` | URL for Triton server | `localhost:8000` |
| `NATS_URL` | URL for NATS connection | `nats://localhost:4222` |
| `NATS_USER` | NATS username | - |
| `NATS_PASSWORD` | NATS password | - |
| `LOG_LEVEL` | Logging level | `info` |
| `MAX_BATCH_SIZE` | Maximum batch size for inference | `16` |
| `CHECKPOINT_DIR` | Directory for model checkpoints | `/checkpoints` |

## Usage

### Running Locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Using Docker

```bash
docker build -t ml-orchestrator-service .
docker run -p 8000:8000 ml-orchestrator-service
```

## Triton Model Configuration

Models in Triton should be configured as follows:

### Summarization Model

```
name: "summarization"
platform: "pytorch_libtorch"
max_batch_size: 16
input [
  {
    name: "TEXT"
    data_type: TYPE_STRING
    dims: [ 1 ]
  }
]
output [
  {
    name: "SUMMARY"
    data_type: TYPE_STRING
    dims: [ 1 ]
  }
]
```

### Entity Extraction Model

```
name: "entity_extraction"
platform: "pytorch_libtorch"
max_batch_size: 16
input [
  {
    name: "TEXT"
    data_type: TYPE_STRING
    dims: [ 1 ]
  }
]
output [
  {
    name: "ENTITIES"
    data_type: TYPE_STRING
    dims: [ -1, 3 ]  # Entity text, type, confidence
  }
]
```

## Example Triton Model Repository Structure

```
model_repository/
├── summarization/
│   ├── 1/
│   │   └── model.pt
│   └── config.pbtxt
└── entity_extraction/
    ├── 1/
    │   └── model.pt
    └── config.pbtxt
```

## Error Handling

- The service implements retry logic for transient failures
- Failed messages are retried with exponential backoff
- Permanent failures are logged and reported via metrics

## Contributing

Contributions are welcome! Please ensure your code follows the project's style guidelines and includes appropriate tests. 