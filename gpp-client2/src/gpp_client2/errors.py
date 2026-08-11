"""
Exceptions raised by the GPP client.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "GPPAuthError",
    "GPPConfigError",
    "GPPConnectionError",
    "GPPError",
    "GPPFieldUnavailableError",
    "GPPGraphQLError",
    "GPPOperationUnavailableError",
    "GPPReadOnlyError",
    "GPPResponseError",
    "GPPRetryableError",
    "GPPTimeoutError",
    "GPPValidationError",
]


class GPPError(Exception):
    """Base class for all exceptions raised by the GPP client."""


class GPPConfigError(GPPError):
    """Raised when client configuration cannot be resolved."""


class GPPAuthError(GPPError):
    """Raised when authentication fails or no token can be resolved."""


class GPPConnectionError(GPPError):
    """Raised when the deployment cannot be reached."""


class GPPTimeoutError(GPPConnectionError):
    """Raised when a request times out."""


class GPPResponseError(GPPError):
    """
    Raised when GPP returns a non-successful HTTP response.

    Parameters
    ----------
    status_code : int
        The HTTP status code.
    message : str
        The error message or response body excerpt.
    """

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"GPP returned HTTP {status_code}: {message}")


class GPPGraphQLError(GPPError):
    """
    Raised when a GraphQL response carries errors.

    Parameters
    ----------
    errors : list[dict[str, Any]]
        The raw GraphQL error objects.
    """

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        messages = (
            "; ".join(str(e.get("message", e)) for e in errors[:5])
            or "unknown GraphQL error"
        )
        if len(errors) > 5:
            messages += f" (+{len(errors) - 5} more)"
        super().__init__(messages)


class GPPOperationUnavailableError(GPPError):
    """
    Raised when an operation is not available in the active environment.

    Parameters
    ----------
    operation_name : str
        The GraphQL operation name.
    environment : str
        The active environment name.
    available_in : tuple[str, ...]
        Environments (schema sources) where the operation is available.
    """

    def __init__(
        self, operation_name: str, environment: str, available_in: tuple[str, ...]
    ):
        self.operation_name = operation_name
        self.environment = environment
        self.available_in = available_in
        super().__init__(
            f"'{operation_name}' is not available in '{environment}' "
            f"(available in: {', '.join(available_in) or 'none'})."
        )


class GPPFieldUnavailableError(GPPError):
    """
    Raised when a raw operation selects a field the active environment does
    not serve.

    Parameters
    ----------
    field_name : str
        The selected field name.
    environment : str
        The active environment name.
    available_in : tuple[str, ...]
        Environments (schema sources) where the field is available.
    """

    def __init__(
        self, field_name: str, environment: str, available_in: tuple[str, ...]
    ):
        self.field_name = field_name
        self.environment = environment
        self.available_in = available_in
        super().__init__(
            f"Field '{field_name}' is not available in '{environment}' "
            f"(available in: {', '.join(available_in) or 'none'})."
        )


class GPPReadOnlyError(GPPError):
    """Raised when a mutation is attempted through a read-only client."""


class GPPRetryableError(GPPError):
    """Raised for transient conditions worth retrying, e.g. a background
    calculation that has not finished yet."""


class GPPValidationError(GPPError):
    """Raised when inputs fail client-side validation before any request."""
