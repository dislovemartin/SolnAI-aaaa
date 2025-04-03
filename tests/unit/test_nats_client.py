"""Unit tests for the NATS client."""
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from nats.aio.msg import Msg

from nats_lib.config import CircuitBreakerConfig, NatsConfig
from nats_lib.nats_client import EnhancedNatsClient


async def test_client_request_success(enhanced_client: EnhancedNatsClient):
    """Test successful request-reply."""
    subject = "test.request"
    payload = {"request": "data"}
    response_data = {"response": "ok"}

    # Mock response message
    mock_msg = AsyncMock(spec=Msg)
    mock_msg.data = json.dumps(response_data).encode()
    enhanced_client._nc.request.return_value = mock_msg

    response = await enhanced_client.request(subject, payload)
    assert response == response_data


async def test_client_subscribe_success(enhanced_client: EnhancedNatsClient):
    """Test successful subscription."""
    subject = "test.subject"
    queue = "test_queue"

    async def callback(msg: Dict[str, Any]) -> None:
        pass

    # Subscribe with the callback
    await enhanced_client.subscribe(subject, callback, queue)

    # Assert that subscribe was called with the correct arguments
    enhanced_client._nc.subscribe.assert_called_once()
    call_args = enhanced_client._nc.subscribe.call_args
    assert call_args[0][0] == subject  # First positional arg is subject
    assert call_args[1]['queue'] == queue  # Keyword arg queue
    assert callable(call_args[1]['cb'])  # Keyword arg cb is callable


@pytest.fixture
async def enhanced_client(mock_nats: AsyncMock) -> EnhancedNatsClient:
    """Create a test enhanced NATS client."""
    config = NatsConfig(
        urls="nats://localhost:4222",
        stream_domain="test",
        publish_breaker=CircuitBreakerConfig(fail_max=3, reset_timeout=1),
        request_breaker=CircuitBreakerConfig(fail_max=3, reset_timeout=1)
    )
    
    with patch("nats_lib.nats_client.nats.connect", return_value=mock_nats):
        client = EnhancedNatsClient(config, "test_service")
        await client.connect()
        yield client


async def test_client_connect_success(
    enhanced_client: EnhancedNatsClient,
    mock_nats: AsyncMock
):
    """Test successful NATS connection."""
    assert enhanced_client.is_connected()
    assert enhanced_client.connected_url == "localhost:4222"
    mock_nats.connect.assert_called_once() 