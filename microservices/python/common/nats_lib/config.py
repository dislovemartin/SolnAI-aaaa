import os
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class CircuitBreakerConfig:
    """Configuration for NATS circuit breaker."""
    fail_max: int = 5  # Maximum number of consecutive failures before opening
    reset_timeout: int = 60  # Time in seconds before attempting to half-open
    exclude_exceptions: tuple = ()  # Exceptions that should not count as failures
    
    @classmethod
    def from_env(cls) -> 'CircuitBreakerConfig':
        """Create config from environment variables."""
        return cls(
            fail_max=int(os.getenv('NATS_CIRCUIT_BREAKER_FAIL_MAX', '5')),
            reset_timeout=int(os.getenv('NATS_CIRCUIT_BREAKER_RESET_TIMEOUT', '60')),
        )

@dataclass
class NatsConfig:
    """Configuration for NATS client."""
    urls: str | list[str]
    user: str | None = None
    password: str | None = None
    token: str | None = None
    use_tls: bool = True
    stream_domain: str = "chimera"
    num_shards: int = 10
    
    # Circuit breaker configs for different operations
    publish_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    request_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    
    @classmethod
    def from_env(cls) -> 'NatsConfig':
        """Create config from environment variables."""
        urls = os.getenv('NATS_URL', 'nats://localhost:4222')
        if ',' in urls:
            urls = [url.strip() for url in urls.split(',')]
            
        return cls(
            urls=urls,
            user=os.getenv('NATS_USER'),
            password=os.getenv('NATS_PASSWORD'),
            token=os.getenv('NATS_TOKEN'),
            use_tls=os.getenv('NATS_USE_TLS', 'true').lower() == 'true',
            stream_domain=os.getenv('NATS_STREAM_DOMAIN', 'chimera'),
            num_shards=int(os.getenv('NATS_NUM_SHARDS', '10')),
            publish_breaker=CircuitBreakerConfig.from_env(),
            request_breaker=CircuitBreakerConfig.from_env(),
        )
