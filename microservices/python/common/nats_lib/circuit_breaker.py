from enum import Enum
from typing import Any, Callable

import pybreaker
from loguru import logger
from prometheus_client import REGISTRY, Counter, Gauge

from .config import CircuitBreakerConfig
from .exceptions import NatsCircuitOpenError


class CircuitBreakerMetrics:
    """Prometheus metrics for circuit breaker state and events."""

    def __init__(
        self,
        service_name: str,
        operation: str,
        subject_pattern: str
    ) -> None:
        """Initialize circuit breaker metrics."""
        # Sanitize metric name components
        service_name = service_name.replace("-", "_").replace(".", "_")
        operation = operation.replace("-", "_").replace(".", "_")
        subject_pattern = subject_pattern.replace("-", "_").replace(".", "_")
        subject_pattern = subject_pattern.replace("*", "all").replace(">", "all")

        # Create metric name prefix
        prefix = f"nats_circuit_breaker_{service_name}_{operation}_{subject_pattern}"

        # Create labels
        labels = {
            "service": service_name,
            "operation": operation,
            "subject_pattern": subject_pattern
        }

        # Initialize metrics
        self.state = Gauge(
            f"{prefix}_state",
            "Current state of the circuit breaker",
            labelnames=list(labels.keys())
        )
        self.total_failures = Counter(
            f"{prefix}_failures_total",
            "Total number of circuit breaker failures",
            labelnames=list(labels.keys())
        )
        self.total_successes = Counter(
            f"{prefix}_successes_total",
            "Total number of circuit breaker successes",
            labelnames=list(labels.keys())
        )
        self.total_state_changes = Counter(
            f"{prefix}_state_changes_total",
            "Total number of circuit breaker state changes",
            labelnames=list(labels.keys())
        )

        # Store labels for later use
        self._labels = labels

        # Register metrics with the default registry
        for metric in [self.state, self.total_failures, self.total_successes, self.total_state_changes]:
            if metric not in REGISTRY._names_to_collectors:
                REGISTRY.register(metric)

        # Set initial state
        self.state.labels(**self._labels).set(CircuitBreakerState.CLOSED.value)

    def record_state_change(self, new_state: CircuitBreakerState) -> None:
        """Record a state change in the circuit breaker."""
        self.state.labels(**self._labels).set(new_state.value)
        self.total_state_changes.labels(**self._labels).inc()
        logger.info(
            "Circuit breaker state changed",
            state=new_state.name,
            **self._labels
        )

    def record_failure(self) -> None:
        """Record a failure in the circuit breaker."""
        self.total_failures.labels(**self._labels).inc()
        logger.debug(
            "Circuit breaker failure",
            **self._labels
        )

    def record_success(self) -> None:
        """Record a success in the circuit breaker."""
        self.total_successes.labels(**self._labels).inc()
        logger.debug(
            "Circuit breaker success",
            **self._labels
        )


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


class CircuitBreakerListener:
    """Listener for circuit breaker state changes."""

    def __init__(self, parent: "NatsCircuitBreaker") -> None:
        """Initialize the listener."""
        self.parent = parent
        self.metrics = CircuitBreakerMetrics(
            self.parent.service_name,
            self.parent.operation,
            self.parent.subject_pattern
        )

    def state_change(self, old_state: str, new_state: str) -> None:
        """Handle state change events."""
        state_map = {
            'closed': CircuitBreakerState.CLOSED,
            'open': CircuitBreakerState.OPEN,
            'half-open': CircuitBreakerState.HALF_OPEN
        }
        
        if new_state in state_map:
            self.metrics.record_state_change(state_map[new_state])
            
            if new_state == 'open':
                logger.error(
                    "Circuit breaker opened",
                    service=self.parent.service_name,
                    operation=self.parent.operation,
                    subject=self.parent.subject_pattern
                )
            elif new_state == 'closed':
                logger.info(
                    "Circuit breaker closed",
                    service=self.parent.service_name,
                    operation=self.parent.operation,
                    subject=self.parent.subject_pattern
                )

    def failure(self, exc: Exception) -> None:
        """Handle failure events."""
        self.metrics.record_failure()

    def success(self) -> None:
        """Handle success events."""
        self.metrics.record_success()


class NatsCircuitBreaker:
    """Circuit breaker for NATS operations."""

    def __init__(
        self,
        service_name: str,
        operation: str,
        subject_pattern: str,
        config: CircuitBreakerConfig
    ) -> None:
        """Initialize the circuit breaker."""
        self.service_name = service_name
        self.operation = operation
        self.subject_pattern = subject_pattern

        # Initialize metrics
        self.metrics = CircuitBreakerMetrics(
            service_name,
            operation,
            subject_pattern
        )

        # Create circuit breaker
        self.breaker = pybreaker.CircuitBreaker(
            fail_max=config.fail_max,
            reset_timeout=config.reset_timeout,
            exclude=config.exclude_exceptions,
            listeners=[CircuitBreakerListener(self)]
        )

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute a function with circuit breaker protection."""
        try:
            result = await self.breaker.call(func, *args, **kwargs)
            self.metrics.record_success()
            return result
        except pybreaker.CircuitBreakerError:
            self.metrics.record_failure()
            raise NatsCircuitOpenError(
                f"Circuit breaker open for {self.operation} on {self.subject_pattern}"
            )
