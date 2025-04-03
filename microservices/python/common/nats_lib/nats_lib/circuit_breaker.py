"""Circuit breaker implementation for NATS operations."""
import enum
from typing import Any, Callable, Dict, Optional

import prometheus_client
import pybreaker
from loguru import logger

from nats_lib.config import CircuitBreakerConfig
from nats_lib.exceptions import NatsCircuitOpenError


class CircuitBreakerState(enum.IntEnum):
    """Circuit breaker states."""
    
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


class CircuitBreakerMetrics:
    """Prometheus metrics for circuit breaker."""

    def __init__(
        self,
        service_name: str,
        operation: str,
        subject_pattern: str
    ):
        """Initialize circuit breaker metrics.

        Args:
            service_name: Name of the service using the circuit breaker.
            operation: Operation being protected (e.g., publish, request).
            subject_pattern: NATS subject pattern being monitored.
        """
        # Sanitize metric name components
        service_name = service_name.replace("-", "_").replace(".", "_")
        operation = operation.replace("-", "_").replace(".", "_")
        subject_pattern = subject_pattern.replace("-", "_").replace(".", "_").replace("*", "all").replace(">", "all")

        # Create metric name prefix
        prefix = f"nats_circuit_breaker_{service_name}_{operation}_{subject_pattern}"

        # Create labels dictionary
        self.labels = {
            "service": service_name,
            "operation": operation,
            "subject_pattern": subject_pattern
        }

        # Initialize metrics
        self.state = prometheus_client.Gauge(
            f"{prefix}_state",
            "Current state of the circuit breaker",
            labelnames=list(self.labels.keys())
        )
        self.total_failures = prometheus_client.Counter(
            f"{prefix}_failures_total",
            "Total number of circuit breaker failures",
            labelnames=list(self.labels.keys())
        )
        self.total_successes = prometheus_client.Counter(
            f"{prefix}_successes_total",
            "Total number of circuit breaker successes",
            labelnames=list(self.labels.keys())
        )
        self.total_state_changes = prometheus_client.Counter(
            f"{prefix}_state_changes_total",
            "Total number of circuit breaker state changes",
            labelnames=list(self.labels.keys()) + ["from_state", "to_state"]
        )

        # Set initial state
        self.state.labels(**self.labels).set(CircuitBreakerState.CLOSED.value)

    def record_state_change(self, old_state: str, new_state: str) -> None:
        """Record a state change in the circuit breaker.

        Args:
            old_state: Previous state name.
            new_state: New state name.
        """
        self.state.labels(**self.labels).set(CircuitBreakerState[new_state].value)
        self.total_state_changes.labels(
            **self.labels,
            from_state=old_state,
            to_state=new_state
        ).inc()
        logger.debug(f"Circuit breaker state changed from {old_state} to {new_state}")

    def record_failure(self) -> None:
        """Record a failure in the circuit breaker."""
        self.total_failures.labels(**self.labels).inc()
        logger.debug("Circuit breaker failure")

    def record_success(self) -> None:
        """Record a success in the circuit breaker."""
        self.total_successes.labels(**self.labels).inc()
        logger.debug("Circuit breaker success")


class NatsCircuitBreaker:
    """Circuit breaker for NATS operations."""
    
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig,
        service_name: str,
        operation: str,
        subject_pattern: str,
    ):
        """Initialize the circuit breaker."""
        self.name = name
        self.config = config
        self.metrics = CircuitBreakerMetrics(
            service_name=service_name,
            operation=operation,
            subject_pattern=subject_pattern,
        )
        
        # Initialize pybreaker
        self.breaker = pybreaker.CircuitBreaker(
            fail_max=config.fail_max,
            reset_timeout=config.reset_timeout,
            exclude=config.exclude_exceptions or (),
            listeners=[self._state_change_listener()],
        )
    
    def _state_change_listener(self) -> pybreaker.CircuitBreakerListener:
        """Create a listener for circuit breaker state changes."""
        class StateChangeListener(pybreaker.CircuitBreakerListener):
            def __init__(self, metrics: CircuitBreakerMetrics):
                self.metrics = metrics
            
            def state_change(self, breaker: pybreaker.CircuitBreaker, old_state: str, new_state: str) -> None:
                state_map = {
                    "closed": CircuitBreakerState.CLOSED,
                    "open": CircuitBreakerState.OPEN,
                    "half-open": CircuitBreakerState.HALF_OPEN,
                }
                
                new_state_value = state_map[new_state]
                self.metrics.state.labels(**self.metrics.labels).set(new_state_value.value)
                
                if new_state == "open":
                    self.metrics.total_state_changes.labels(
                        **self.metrics.labels,
                        from_state=old_state,
                        to_state=new_state
                    ).inc()
                
                logger.info(
                    f"Circuit breaker state changed from {old_state} to {new_state}",
                    breaker=breaker.name,
                    old_state=old_state,
                    new_state=new_state,
                )
            
            def failure(self, breaker: pybreaker.CircuitBreaker, exc: Exception) -> None:
                self.metrics.total_failures.labels(**self.metrics.labels).inc()
                logger.warning(
                    f"Circuit breaker failure",
                    breaker=breaker.name,
                    error=str(exc),
                )
            
            def success(self, breaker: pybreaker.CircuitBreaker) -> None:
                self.metrics.total_successes.labels(**self.metrics.labels).inc()
                logger.debug(
                    f"Circuit breaker success",
                    breaker=breaker.name,
                )
        
        return StateChangeListener(self.metrics)
    
    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Call a function through the circuit breaker."""
        try:
            return await self.breaker.call(func, *args, **kwargs)
        except pybreaker.CircuitBreakerError:
            raise NatsCircuitOpenError(f"Circuit breaker {self.name} is open") 