"""Circuit breaker implementation for NATS operations."""
from enum import Enum
from typing import Any, Callable

import prometheus_client
import pybreaker
from loguru import logger

from nats_lib.exceptions import NatsCircuitOpenError


class CircuitBreakerState(Enum):
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
        """Initialize circuit breaker metrics."""
        # Sanitize metric name components
        service_name = service_name.replace('-', '_').replace('.', '_')
        operation = (operation.replace('-', '_').replace('.', '_')
                    .replace('*', 'all'))
        subject_pattern = (subject_pattern.replace('-', '_').replace('.', '_')
                         .replace('*', 'all'))

        # Create metric name prefix
        prefix = f"nats_circuit_breaker_{service_name}_{operation}_{subject_pattern}"

        # Labels for all metrics
        self.labels = {
            'service': service_name,
            'operation': operation,
            'subject_pattern': subject_pattern
        }

        # Initialize metrics directly with the default registry
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
            labelnames=list(self.labels.keys())
        )
        self.opens = prometheus_client.Counter(
            f"{prefix}_opens_total",
            "Total number of times the circuit breaker has opened",
            labelnames=list(self.labels.keys())
        )

        # Set initial state
        self.state.labels(**self.labels).set(CircuitBreakerState.CLOSED.value)

    def record_state_change(self, old_state: str, new_state: str) -> None:
        """Record a state change in the circuit breaker."""
        self.total_state_changes.labels(**self.labels).inc()
        self.state.labels(**self.labels).set(CircuitBreakerState[new_state].value)
        if new_state == "OPEN":
            self.opens.labels(**self.labels).inc()
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
        config: Any,
        service_name: str,
        operation: str,
        subject_pattern: str
    ):
        """Initialize the circuit breaker.

        Args:
            name: Name of the circuit breaker.
            config: Circuit breaker configuration.
            service_name: Name of the service using the circuit breaker.
            operation: Operation being protected (e.g., publish, request).
            subject_pattern: NATS subject pattern being monitored.
        """
        self.metrics = CircuitBreakerMetrics(
            service_name=service_name,
            operation=operation,
            subject_pattern=subject_pattern
        )

        self.breaker = pybreaker.CircuitBreaker(
            fail_max=config.fail_max,
            reset_timeout=config.reset_timeout,
            exclude=[exc for exc in config.exclude_exceptions],
            listeners=[self._state_change_listener()]
        )

    def _state_change_listener(self) -> pybreaker.CircuitBreakerListener:
        """Create a listener for circuit breaker state changes.

        Returns:
            CircuitBreakerListener that updates metrics on state changes.
        """
        class MetricsListener(pybreaker.CircuitBreakerListener):
            def __init__(self, metrics: CircuitBreakerMetrics):
                self.metrics = metrics

            def state_change(self, cb: pybreaker.CircuitBreaker, old_state: str, new_state: str):
                """Handle state change event."""
                from_state = CircuitBreakerState[old_state.upper()]
                to_state = CircuitBreakerState[new_state.upper()]
                self.metrics.record_state_change(from_state.name, to_state.name)
                logger.debug(f"Circuit breaker state changed from {old_state} to {new_state}")

            def failure(self, cb: pybreaker.CircuitBreaker, exc: Exception):
                """Handle failure event."""
                self.metrics.record_failure()
                logger.debug(f"Circuit breaker failure: {exc}")

            def success(self, cb: pybreaker.CircuitBreaker):
                """Handle success event."""
                self.metrics.record_success()
                logger.debug("Circuit breaker success")

        return MetricsListener(self.metrics)

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function through the circuit breaker.

        Args:
            func: Function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            Result of the function call.

        Raises:
            NatsCircuitOpenError: If the circuit breaker is open.
            Exception: Any exception raised by the function.
        """
        try:
            return await self.breaker.call(func, *args, **kwargs)
        except pybreaker.CircuitBreakerError as e:
            raise NatsCircuitOpenError(str(e)) from e 