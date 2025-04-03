"""Configuration classes for the NATS client."""
from dataclasses import dataclass
from typing import Optional, Tuple, Type


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    
    fail_max: int = 3
    reset_timeout: int = 60
    exclude_exceptions: Optional[Tuple[Type[Exception], ...]] = None


@dataclass
class NatsConfig:
    """NATS client configuration."""
    
    urls: str
    stream_domain: str
    publish_breaker: CircuitBreakerConfig
    request_breaker: CircuitBreakerConfig
    user: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    use_tls: bool = False
    request_timeout: int = 30
    num_shards: int = 1 