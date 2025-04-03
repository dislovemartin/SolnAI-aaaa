# Ingestion Service

A high-performance Rust microservice for data ingestion and validation, designed to efficiently process incoming data and publish it to NATS streams for further processing.

## Features

- Fast and efficient data ingestion using Rust and Axum
- Single-item and batch ingestion endpoints
- Validation and preprocessing of incoming data
- Publication to NATS streams for downstream processing
- Structured error handling with detailed responses
- Health check endpoint for monitoring
- CORS support for web clients

## Components

- **Axum Web Framework**: Provides HTTP server and routing
- **NATS Client**: Handles message publishing to NATS streams
- **Custom Error Handling**: Structured error types and responses
- **Data Models**: Type-safe request and response models

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check endpoint |
| `/ingest` | POST | Single-item ingestion endpoint |
| `/ingest/batch` | POST | Batch ingestion endpoint |

## Request and Response Format

### Single-Item Ingestion

**Request:**
```json
{
  "id": "optional-custom-id",
  "source": "source-name",
  "content_type": "research_paper",
  "payload": {
    "title": "Example Research Paper",
    "text": "This is the content of the research paper...",
    "metadata": {
      "author": "John Doe",
      "published_date": "2023-03-15"
    }
  }
}
```

**Response (Success):**
```json
{
  "id": "generated-or-custom-id",
  "status": "success",
  "timestamp": "2023-03-16T10:15:30Z"
}
```

### Batch Ingestion

**Request:**
```json
{
  "items": [
    {
      "id": "item-1",
      "source": "source-name",
      "content_type": "research_paper",
      "payload": { ... }
    },
    {
      "id": "item-2",
      "source": "source-name",
      "content_type": "news_article",
      "payload": { ... }
    }
  ]
}
```

**Response (Success):**
```json
{
  "success_count": 2,
  "error_count": 0,
  "results": [
    {
      "id": "item-1",
      "status": "success",
      "timestamp": "2023-03-16T10:15:30Z"
    },
    {
      "id": "item-2",
      "status": "success",
      "timestamp": "2023-03-16T10:15:30Z"
    }
  ]
}
```

## NATS Message Format

The service publishes messages to NATS with the following format:

```json
{
  "id": "item-id",
  "source": "source-name",
  "content_type": "research_paper",
  "timestamp": "2023-03-16T10:15:30Z",
  "payload": {
    "title": "Example Research Paper",
    "text": "This is the content of the research paper...",
    "metadata": {
      "author": "John Doe",
      "published_date": "2023-03-15"
    }
  }
}
```

Messages are published to subjects following the pattern: `ingest.validated.{content_type}`

## Requirements

- Rust 1.60+ (2021 edition)
- NATS Server 2.2+

## Dependencies

Major dependencies include:
- `axum`: Web framework
- `tokio`: Async runtime
- `serde`: Serialization/deserialization
- `async-nats`: NATS client
- `tower-http`: Middleware for HTTP
- `tracing`: Logging and diagnostics

## Installation

1. Clone the repository
2. Build the service:

```bash
cargo build --release
```

## Configuration

The service is configured using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `NATS_URL` | URL for NATS connection | `nats://localhost:4222` |
| `PORT` | HTTP server port | `3000` |
| `RUST_LOG` | Logging level | `info,tower_http=debug` |

## Usage

### Running Locally

```bash
cargo run --release
```

### Using Docker

```bash
docker build -t ingestion-service .
docker run -p 3000:3000 ingestion-service
```

## Performance Considerations

- The service is designed for high throughput with asynchronous processing
- Batch ingestion should be preferred for high-volume data processing
- Connection pooling is used for NATS to reduce overhead
- Error handling is designed to be graceful under load

## Error Handling

The service provides structured error responses:

```json
{
  "error": "validation_error",
  "message": "Invalid payload format",
  "details": "field 'text' is required"
}
```

Common error types include:
- `validation_error`: Invalid request format or data
- `internal_error`: Server-side processing error
- `nats_error`: Error communicating with NATS

## Testing

Run the test suite with:

```bash
cargo test
```

## Contributing

Contributions are welcome! Please ensure your code follows the project's style guidelines and includes appropriate tests. 