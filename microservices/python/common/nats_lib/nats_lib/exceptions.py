"""Custom exceptions for the NATS client."""


class NatsError(Exception):
    """Base exception for NATS client errors."""


class NatsConnectionError(NatsError):
    """Raised when there is an error connecting to NATS."""


class NatsCircuitOpenError(NatsError):
    """Raised when a circuit breaker is open."""


class NatsPublishError(NatsError):
    """Raised when there is an error publishing a message."""


class NatsSubscribeError(NatsError):
    """Raised when there is an error subscribing to a subject."""


class NatsRequestError(NatsError):
    """Raised when there is an error making a request.""" 