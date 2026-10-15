"""Errors shared by the application core and its transport adapters."""


class DomainError(Exception):
    """An expected failure represented independently of HTTP or CLI conventions."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class FeatureNotImplemented(NotImplementedError):
    """Explicitly identify scaffolded operations rather than return fake results."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"{operation} is scaffolded but not implemented yet.")
