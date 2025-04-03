class NatsLibError(Exception):
    """Base exception for NATS library errors."""
    pass


class NatsCircuitOpenError(NatsLibError):
    """Exception raised when a circuit breaker is open."""
    def __init__(self, operation: str, subject: str):
        self.operation = operation
        self.subject = subject
        super().__init__(
            f"Circuit breaker is open for {operation} operation on subject {subject}"
        )


class NatsConnectionError(NatsLibError):
    """Exception raised when there are NATS connection issues."""
    pass


class NatsTimeoutError(NatsLibError):
    """Exception raised when a NATS operation times out."""
    pass


class NatsOperationError(NatsLibError):
    """Exception raised when a NATS operation fails."""
    pass
