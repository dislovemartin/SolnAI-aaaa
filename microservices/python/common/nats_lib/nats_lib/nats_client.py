"""Enhanced NATS client with circuit breaker support."""
import json
from typing import Any, Callable, Dict, Optional, Union

import nats
from loguru import logger
from nats.js.api import StreamConfig
from nats_lib.circuit_breaker import NatsCircuitBreaker
from nats_lib.config import NatsConfig
from nats_lib.exceptions import (NatsCircuitOpenError, NatsConnectionError,
                                 NatsPublishError, NatsRequestError,
                                 NatsSubscribeError)


class EnhancedNatsClient:
    """Enhanced NATS client with circuit breaker support."""
    
    def __init__(self, config: NatsConfig, service_name: str):
        """Initialize the enhanced NATS client."""
        self._config = config
        self._service_name = service_name
        self._nc = None
        self._js = None
        
        # Initialize circuit breakers
        self._publish_breaker = NatsCircuitBreaker(
            name=f"{service_name}_publish",
            config=config.publish_breaker,
            service_name=service_name,
            operation="publish",
            subject_pattern="*",
        )
        
        self._request_breaker = NatsCircuitBreaker(
            name=f"{service_name}_request",
            config=config.request_breaker,
            service_name=service_name,
            operation="request",
            subject_pattern="*",
        )
    
    async def connect(self) -> None:
        """Connect to NATS server."""
        try:
            self._nc = await nats.connect(
                servers=self._config.urls.split(","),
                user=self._config.user,
                password=self._config.password,
                token=self._config.token,
                tls=self._config.use_tls,
            )
            self._js = await self._nc.jetstream()
            logger.info(
                "Connected to NATS",
                url=self.connected_url,
                service=self._service_name,
            )
        except Exception as e:
            logger.error(
                "Failed to connect to NATS",
                error=str(e),
                service=self._service_name,
            )
            raise NatsConnectionError(f"Failed to connect to NATS: {e}")
    
    async def close(self) -> None:
        """Close NATS connection."""
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
    
    def is_connected(self) -> bool:
        """Check if connected to NATS."""
        return self._nc is not None and not self._nc.is_closed
    
    @property
    def connected_url(self) -> Optional[str]:
        """Get the connected server URL."""
        if self.is_connected() and self._nc.connected_url:
            return self._nc.connected_url.netloc
        return None
    
    async def publish(self, subject: str, payload: Dict[str, Any]) -> None:
        """Publish a message with circuit breaker protection."""
        if not self.is_connected():
            raise NatsConnectionError("Not connected to NATS")
        
        async def _publish() -> None:
            try:
                await self._nc.publish(
                    subject,
                    json.dumps(payload).encode(),
                )
            except Exception as e:
                logger.error(
                    "Failed to publish message",
                    subject=subject,
                    error=str(e),
                    service=self._service_name,
                )
                raise NatsPublishError(f"Failed to publish message: {e}")
        
        try:
            await self._publish_breaker.call(_publish)
        except NatsCircuitOpenError as e:
            logger.error(
                "Circuit breaker open for publish",
                subject=subject,
                service=self._service_name,
            )
            raise
    
    async def request(
        self,
        subject: str,
        payload: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Make a request with circuit breaker protection."""
        if not self.is_connected():
            raise NatsConnectionError("Not connected to NATS")
        
        async def _request() -> Dict[str, Any]:
            try:
                response = await self._nc.request(
                    subject,
                    json.dumps(payload).encode(),
                    timeout=timeout or self._config.request_timeout,
                )
                return json.loads(response.data.decode())
            except Exception as e:
                logger.error(
                    "Failed to make request",
                    subject=subject,
                    error=str(e),
                    service=self._service_name,
                )
                raise NatsRequestError(f"Failed to make request: {e}")
        
        try:
            return await self._request_breaker.call(_request)
        except NatsCircuitOpenError as e:
            logger.error(
                "Circuit breaker open for request",
                subject=subject,
                service=self._service_name,
            )
            raise
    
    async def subscribe(
        self,
        subject: str,
        callback: Callable[[Dict[str, Any]], None],
        queue: Optional[str] = None,
    ) -> None:
        """Subscribe to a subject."""
        if not self.is_connected():
            raise NatsConnectionError("Not connected to NATS")
        
        async def _message_handler(msg: nats.aio.msg.Msg) -> None:
            try:
                payload = json.loads(msg.data.decode())
                await callback(payload)
            except Exception as e:
                logger.error(
                    "Error in message handler",
                    subject=subject,
                    error=str(e),
                    service=self._service_name,
                )
        
        try:
            await self._nc.subscribe(
                subject,
                queue=queue,
                cb=_message_handler,
            )
            logger.info(
                "Subscribed to subject",
                subject=subject,
                queue=queue,
                service=self._service_name,
            )
        except Exception as e:
            logger.error(
                "Failed to subscribe",
                subject=subject,
                error=str(e),
                service=self._service_name,
            )
            raise NatsSubscribeError(f"Failed to subscribe: {e}")
    
    def _wrap_subscriber_callback(
        self,
        callback: Callable[[Dict[str, Any]], None],
    ) -> Callable[[nats.aio.msg.Msg], None]:
        """Wrap a subscriber callback to handle message decoding."""
        async def _wrapper(msg: nats.aio.msg.Msg) -> None:
            try:
                payload = json.loads(msg.data.decode())
                await callback(payload)
            except Exception as e:
                logger.error(
                    "Error in subscriber callback",
                    error=str(e),
                    service=self._service_name,
                )
        return _wrapper 