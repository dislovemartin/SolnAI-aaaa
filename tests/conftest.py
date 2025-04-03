"""Test configuration and fixtures for nats_lib tests."""
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest
from prometheus_client import REGISTRY

from nats_lib.config import CircuitBreakerConfig, NatsConfig


@pytest.fixture
def clean_prometheus_registry():
    """Clean up the Prometheus registry before each test."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def circuit_breaker_config():
    """Create a test circuit breaker configuration."""
    return CircuitBreakerConfig(
        fail_max=3,
        reset_timeout=1,
        exclude_exceptions=(ValueError,)
    )


@pytest.fixture
def nats_config():
    """Create a test NATS configuration."""
    return NatsConfig(
        urls="nats://localhost:4222",
        stream_domain="test",
        publish_breaker=CircuitBreakerConfig(fail_max=3, reset_timeout=1),
        request_breaker=CircuitBreakerConfig(fail_max=3, reset_timeout=1)
    )


@pytest.fixture
def mock_nats() -> AsyncMock:
    """Create a mock NATS client."""
    mock = AsyncMock()
    
    # Create JetStream mock that can be awaited
    js_mock = AsyncMock()
    js_mock.publish = AsyncMock()
    js_mock.subscribe = AsyncMock()
    js_mock.request = AsyncMock()
    
    # Make jetstream() an AsyncMock that returns the js_mock
    mock.jetstream = AsyncMock(return_value=js_mock)
    
    # Set up other mock methods
    mock.publish = AsyncMock()
    mock.subscribe = AsyncMock()
    mock.request = AsyncMock()
    mock.connected_url = "localhost:4222"
    mock.is_closed = False
    
    return mock


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean up the Prometheus registry before each test."""
    REGISTRY.clear() 