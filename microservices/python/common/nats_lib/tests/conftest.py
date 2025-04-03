"""Test configuration and fixtures for nats_lib tests."""
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest
from prometheus_client import REGISTRY

from nats_lib.config import CircuitBreakerConfig, NatsConfig


@pytest.fixture(autouse=True)
def clean_prometheus_registry():
    """Clean up Prometheus registry before each test."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for each test."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def circuit_breaker_config() -> CircuitBreakerConfig:
    """Create a test circuit breaker configuration."""
    return CircuitBreakerConfig(
        fail_max=3,
        reset_timeout=1,
        exclude_exceptions=(ValueError,)
    )


@pytest.fixture
def nats_config(circuit_breaker_config: CircuitBreakerConfig) -> NatsConfig:
    """Create a test NATS configuration."""
    return NatsConfig(
        urls="nats://localhost:4222",
        user="test_user",
        password="test_pass",
        stream_domain="test_domain",
        publish_breaker=circuit_breaker_config,
        request_breaker=circuit_breaker_config
    )


@pytest.fixture
async def mock_nats() -> AsyncGenerator[AsyncMock, None]:
    """Create a mock NATS client."""
    with patch("nats.connect") as mock_connect:
        # Create an async mock for the NATS client
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.connected_url = urlparse("nats://localhost:4222")
        
        # Create an async mock for JetStream
        mock_js = AsyncMock()
        
        # Set up JetStream mock to return a coroutine
        async def mock_jetstream():
            return mock_js
        mock_client.jetstream = mock_jetstream
        
        # Set up connect mock to return a coroutine
        async def mock_connect_coro(*args, **kwargs):
            return mock_client
        mock_connect.side_effect = mock_connect_coro
        
        # Set up subscribe mock to store the callback
        def subscribe_side_effect(*args, **kwargs):
            mock_client._last_callback = kwargs.get('cb')
            return AsyncMock()
        mock_client.subscribe.side_effect = subscribe_side_effect
        
        # Set up publish mock to return a coroutine
        async def publish_coro(*args, **kwargs):
            return None
        mock_client.publish.side_effect = publish_coro
        
        # Set up request mock to return a coroutine
        async def request_coro(*args, **kwargs):
            return AsyncMock(data=b'{"response": "ok"}')
        mock_client.request.side_effect = request_coro
        
        yield mock_client 