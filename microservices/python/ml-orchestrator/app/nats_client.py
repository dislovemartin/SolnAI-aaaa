"""NATS client wrapper for ML orchestrator service."""
from typing import List, Optional, Union

from nats_lib import EnhancedNatsClient, NatsConfig


class MLOrchestratorNatsClient(EnhancedNatsClient):
    """ML orchestrator specific NATS client."""
    
    def __init__(
        self,
        nats_urls: Union[str, List[str]],
        use_tls: bool = True,
        user: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        stream_domain: str = "chimera",
        num_shards: int = 10,
    ):
        """Initialize the NATS client.
        
        Args:
            nats_urls: URL(s) of the NATS server
            use_tls: Whether to use TLS for connection
            user: Optional username for authentication
            password: Optional password for authentication
            token: Optional token for authentication
            stream_domain: JetStream domain
            num_shards: Number of shards for high-throughput streams
        """
        config = NatsConfig(
            urls=nats_urls,
            use_tls=use_tls,
            user=user,
            password=password,
            token=token,
            stream_domain=stream_domain,
            num_shards=num_shards,
        )
        
        super().__init__(
            config=config,
            service_name="ml-orchestrator",
        )
