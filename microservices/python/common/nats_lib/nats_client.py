import asyncio
import json
import os
from typing import Any, Callable, Dict, List, Optional, Union

import nats
from loguru import logger
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg
from nats.js.api import ConsumerConfig
from nats.js.client import JetStreamContext

from .circuit_breaker import NatsCircuitBreaker
from .config import NatsConfig
from .exceptions import (NatsCircuitOpenError, NatsConnectionError,
                         NatsOperationError, NatsTimeoutError)


class EnhancedNatsClient:
    """Enhanced NATS client with circuit breaker support."""

    def __init__(
        self,
        config: NatsConfig,
        service_name: str,
    ):
        """Initialize the NATS client.
        
        Args:
            config: NATS configuration
            service_name: Name of the service using this client
        """
        self.config = config
        self.service_name = service_name
        
        # NATS connection objects
        self.nc: Optional[NATS] = None
        self.js: Optional[JetStreamContext] = None
        
        # Circuit breakers
        self.publish_breaker = NatsCircuitBreaker(
            name=f"{service_name}_publish",
            config=config.publish_breaker,
            service_name=service_name,
            operation="publish",
            subject_pattern="*"  # Wildcard for all subjects
        )
        
        self.request_breaker = NatsCircuitBreaker(
            name=f"{service_name}_request",
            config=config.request_breaker,
            service_name=service_name,
            operation="request",
            subject_pattern="*"  # Wildcard for all subjects
        )
        
        # Track subscriptions for reconnection
        self._subscriptions: List[Dict[str, Any]] = []

    async def connect(self) -> None:
        """Connect to the NATS server."""
        try:
            # Set up connection options
            options = {
                "servers": (
                    [self.config.urls]
                    if isinstance(self.config.urls, str)
                    else self.config.urls
                ),
                "reconnected_cb": self._on_reconnected,
                "disconnected_cb": self._on_disconnected,
                "error_cb": self._on_error,
                "closed_cb": self._on_closed,
                "max_reconnect_attempts": -1,  # Unlimited reconnect attempts
                "reconnect_time_wait": 2,  # Seconds between reconnect attempts
            }
            
            # Add authentication if provided
            if self.config.user and self.config.password:
                options["user"] = self.config.user
                options["password"] = self.config.password
            elif self.config.token:
                options["token"] = self.config.token
                
            # Add TLS if enabled
            if self.config.use_tls:
                tls_config = {
                    "ca_file": os.getenv(
                        "NATS_CA_FILE", "/etc/nats/certs/ca.crt"
                    ),
                    "cert_file": os.getenv(
                        "NATS_CERT_FILE", "/etc/nats/certs/client.crt"
                    ),
                    "key_file": os.getenv(
                        "NATS_KEY_FILE", "/etc/nats/certs/client.key"
                    ),
                }
                options["tls"] = tls_config
            
            # Connect to NATS
            self.nc = await nats.connect(**options)
            logger.info(f"Connected to NATS at {self.nc.connected_url.netloc}")
            
            # Initialize JetStream
            self.js = self.nc.jetstream(domain=self.config.stream_domain)
            logger.info(
                f"JetStream initialized with domain '{self.config.stream_domain}'"
            )
            
            # Restore subscriptions if any
            for sub in self._subscriptions:
                await self.subscribe(**sub)
            
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            self.nc = None
            self.js = None
            raise NatsConnectionError(f"Failed to connect to NATS: {e}")

    async def close(self) -> None:
        """Close the NATS connection."""
        if self.nc:
            try:
                await self.nc.drain()
                await self.nc.close()
            except Exception as e:
                logger.error(f"Error closing NATS connection: {e}")
            finally:
                self.nc = None
                self.js = None

    def is_connected(self) -> bool:
        """Check if connected to NATS."""
        return self.nc is not None and not self.nc.is_closed

    async def publish(
        self,
        subject: str,
        payload: Union[str, bytes, Dict[str, Any]],
        headers: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Publish a message with circuit breaker protection.
        
        Args:
            subject: Subject to publish to
            payload: Message payload
            headers: Optional message headers
            
        Returns:
            JetStream publish response if available
            
        Raises:
            NatsCircuitOpenError: If circuit breaker is open
            NatsConnectionError: If not connected to NATS
            NatsOperationError: If publish fails
        """
        if not self.is_connected():
            raise NatsConnectionError("Not connected to NATS")
            
        # Prepare payload
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        if isinstance(payload, str):
            payload = payload.encode()
            
        try:
            # Publish with circuit breaker protection
            if self.js:
                result = await self.publish_breaker.call(
                    self.js.publish,
                    subject,
                    payload,
                    headers=headers
                )
                return {
                    "stream": result.stream,
                    "seq": result.seq,
                    "duplicate": result.duplicate,
                }
            else:
                await self.publish_breaker.call(
                    self.nc.publish,
                    subject,
                    payload,
                    headers=headers
                )
                return None
                
        except NatsCircuitOpenError:
            raise
        except Exception as e:
            logger.error(f"Failed to publish to {subject}: {e}")
            raise NatsOperationError(f"Failed to publish to {subject}: {e}")

    async def request(
        self,
        subject: str,
        payload: Union[str, bytes, Dict[str, Any]],
        timeout: float = 10.0,
        headers: Optional[Dict[str, str]] = None
    ) -> bytes:
        """Send a request with circuit breaker protection.
        
        Args:
            subject: Subject to send request to
            payload: Request payload
            timeout: Request timeout in seconds
            headers: Optional message headers
            
        Returns:
            Response data
            
        Raises:
            NatsCircuitOpenError: If circuit breaker is open
            NatsConnectionError: If not connected to NATS
            NatsTimeoutError: If request times out
            NatsOperationError: If request fails
        """
        if not self.is_connected():
            raise NatsConnectionError("Not connected to NATS")
            
        # Prepare payload
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        if isinstance(payload, str):
            payload = payload.encode()
            
        try:
            # Send request with circuit breaker protection
            msg = await self.request_breaker.call(
                self.nc.request,
                subject,
                payload,
                timeout=timeout,
                headers=headers
            )
            return msg.data
            
        except NatsCircuitOpenError:
            raise
        except asyncio.TimeoutError:
            logger.warning(f"Request to {subject} timed out after {timeout}s")
            raise NatsTimeoutError(f"Request to {subject} timed out")
        except Exception as e:
            logger.error(f"Failed to send request to {subject}: {e}")
            raise NatsOperationError(f"Failed to send request to {subject}: {e}")

    async def subscribe(
        self,
        subject: str,
        callback: Callable[[Msg], Any],
        queue: Optional[str] = None,
        durable: bool = True,
        max_in_flight: int = 100,
    ) -> None:
        """Subscribe to a subject.
        
        Args:
            subject: Subject to subscribe to
            callback: Message handler function
            queue: Optional queue group
            durable: Whether to use durable subscription
            max_in_flight: Maximum in-flight messages
            
        Raises:
            NatsConnectionError: If not connected to NATS
            NatsOperationError: If subscription fails
        """
        if not self.is_connected():
            raise NatsConnectionError("Not connected to NATS")
            
        try:
            # Skip if already subscribed
            for sub in self._subscriptions:
                if (
                    sub["subject"] == subject
                    and sub["queue"] == queue
                    and sub["callback"] == callback
                ):
                    logger.debug(f"Already subscribed to {subject}")
                    return
            
            # Store subscription for reconnection
            sub_info = {
                "subject": subject,
                "callback": callback,
                "queue": queue,
                "durable": durable,
                "max_in_flight": max_in_flight,
            }
            
            if self.js:
                # Create consumer name
                consumer = (
                    f"{self.service_name}-{subject.replace('.', '-')}"
                    + (f"-{queue}" if queue else "")
                )
                
                # Subscribe with JetStream
                await self.js.subscribe(
                    subject,
                    queue=queue,
                    cb=callback,
                    stream=self.config.stream_domain,
                    config=ConsumerConfig(
                        durable_name=consumer if durable else None,
                        ack_policy="explicit",
                        ack_wait=30,
                        max_ack_pending=max_in_flight,
                        deliver_policy="all",
                    ),
                )
                
                logger.info(
                    f"Subscribed to {subject} with JetStream"
                    + (f" (queue: {queue})" if queue else "")
                )
            else:
                # Standard NATS subscription
                await self.nc.subscribe(
                    subject,
                    queue=queue,
                    cb=callback,
                )
                
                logger.info(
                    f"Subscribed to {subject}"
                    + (f" (queue: {queue})" if queue else "")
                )
            
            self._subscriptions.append(sub_info)
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {subject}: {e}")
            raise NatsOperationError(f"Failed to subscribe to {subject}: {e}")

    def _on_reconnected(self) -> None:
        """Handle NATS reconnection."""
        logger.info("Reconnected to NATS")

    def _on_disconnected(self) -> None:
        """Handle NATS disconnection."""
        logger.warning("Disconnected from NATS")

    def _on_error(self, e: Exception) -> None:
        """Handle NATS errors."""
        logger.error(f"NATS error: {e}")

    def _on_closed(self) -> None:
        """Handle NATS connection closure."""
        logger.info("NATS connection closed")
        self.nc = None
        self.js = None
