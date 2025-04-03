"""NATS client wrapper for knowledge graph service."""
from typing import Optional

from nats_lib import EnhancedNatsClient, NatsConfig


class KnowledgeGraphNatsClient(EnhancedNatsClient):
    """Knowledge graph specific NATS client."""
    
    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """Initialize the NATS client.
        
        Args:
            nats_url: URL of the NATS server
            user: Optional username for authentication
            password: Optional password for authentication
        """
        config = NatsConfig(
            urls=nats_url,
            user=user,
            password=password,
            stream_domain="chimera",
        )
        
        super().__init__(
            config=config,
            service_name="knowledge-graph",
        )
