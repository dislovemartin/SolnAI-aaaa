import pytest

from nats_lib.circuit_breaker import NatsCircuitBreaker


@pytest.fixture
def circuit_breaker(circuit_breaker_config) -> NatsCircuitBreaker:
    """Create a test circuit breaker instance."""
    return NatsCircuitBreaker(
        name="test_breaker",
        service_name="test_service",
        operation="test_op",
        subject_pattern="test.subject",
        config=circuit_breaker_config
    )