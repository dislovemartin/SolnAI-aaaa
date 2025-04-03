# NATS Library with Circuit Breaker Support

This library provides an enhanced NATS client implementation with circuit breaker support for Python microservices.

## Features

- Circuit breaker pattern implementation using `pybreaker`
- Prometheus metrics for monitoring circuit breaker states and events
- Support for both standard NATS and JetStream operations
- Configurable circuit breaker parameters via environment variables
- TLS support with configurable certificates
- Automatic reconnection handling
- Subscription persistence across reconnections
- Comprehensive error handling and logging

## Installation

Add the following to your `requirements.txt`:

```
-e ../common/nats_lib
```

## Configuration

The library can be configured using environment variables:

### Circuit Breaker Configuration

- `NATS_CIRCUIT_BREAKER_FAIL_MAX`: Maximum number of consecutive failures before opening (default: 5)
- `NATS_CIRCUIT_BREAKER_RESET_TIMEOUT`: Time in seconds before attempting to half-open (default: 60)

### NATS Configuration

- `NATS_URL`: NATS server URL(s), comma-separated for multiple servers
- `NATS_USER`: NATS username for authentication
- `NATS_PASSWORD`: NATS password for authentication
- `NATS_TOKEN`: Alternative token-based authentication
- `NATS_USE_TLS`: Whether to use TLS (default: true)
- `NATS_STREAM_DOMAIN`: JetStream domain (default: "chimera")
- `NATS_NUM_SHARDS`: Number of shards for high-throughput streams (default: 10)

### TLS Configuration

- `NATS_CA_FILE`: Path to CA certificate (default: "/etc/nats/certs/ca.crt")
- `NATS_CERT_FILE`: Path to client certificate (default: "/etc/nats/certs/client.crt")
- `NATS_KEY_FILE`: Path to client key (default: "/etc/nats/certs/client.key")

## Usage

```python
from nats_lib import EnhancedNatsClient, NatsConfig

# Create configuration
config = NatsConfig(
    urls="nats://localhost:4222",
    user="myuser",
    password="mypass",
    stream_domain="myapp"
)

# Initialize client
client = EnhancedNatsClient(
    config=config,
    service_name="my-service"
)

# Connect to NATS
await client.connect()

# Publish with circuit breaker protection
try:
    await client.publish("my.subject", {"key": "value"})
except NatsCircuitOpenError:
    # Handle circuit breaker open state
    pass

# Subscribe to subjects
await client.subscribe(
    subject="my.subject",
    callback=my_message_handler,
    queue="my-queue",
    durable=True
)

# Send request with circuit breaker protection
try:
    response = await client.request("my.service", "request payload")
except NatsCircuitOpenError:
    # Handle circuit breaker open state
    pass
except NatsTimeoutError:
    # Handle request timeout
    pass

# Close connection
await client.close()
```

## Prometheus Metrics

The library exports the following Prometheus metrics:

- `nats_circuit_breaker_state`: Circuit breaker state (0=closed, 1=open, 2=half-open)
- `nats_circuit_breaker_opens_total`: Number of times circuit breaker opened
- `nats_circuit_breaker_rejected_calls_total`: Number of calls rejected due to open circuit

Labels:

- `service`: Name of the service
- `operation`: Operation type (publish/request)
- `subject_pattern`: NATS subject pattern

## Error Handling

The library provides custom exceptions for different error scenarios:

- `NatsCircuitOpenError`: Raised when a circuit breaker is open
- `NatsConnectionError`: Raised for connection issues
- `NatsTimeoutError`: Raised when a request times out
- `NatsOperationError`: Raised for other NATS operation failures

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for your changes
5. Run the test suite
6. Create a pull request
