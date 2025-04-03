"""NATS client wrapper for personalization engine."""
from typing import Optional

from nats_lib import EnhancedNatsClient, NatsConfig


class PersonalizationNatsClient(EnhancedNatsClient):
    """Personalization engine specific NATS client."""
    
    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        user: Optional[str] = None,
        password: Optional[str] = None,
        stream_name: str = "chimera",
        consumer_name: str = "personalization-engine",
    ):
        """Initialize the NATS client.
        
        Args:
            nats_url: URL of the NATS server
            user: Optional username for authentication
            password: Optional password for authentication
            stream_name: Name of the JetStream stream
            consumer_name: Name of the JetStream consumer
        """
        config = NatsConfig(
            urls=nats_url,
            user=user,
            password=password,
            stream_domain=stream_name,
        )
        
        super().__init__(
            config=config,
            service_name=consumer_name,
        )
