"""
Exceptions raised by the GPP client.

The transport and GraphQL errors are the vendored gqlforge runtime's,
re-exported from :mod:`gpp_client2._generated._exceptions`: one base,
``ClientError``, so a single ``except`` catches everything the client
raises. The ``GPP*`` classes below are GPP-specific and subclass
``ClientError`` too.
"""

from __future__ import annotations

from gpp_client2._generated._exceptions import (
    AuthError,
    ClientError,
    GraphQLResponseError,
    OperationUnavailableError,
    ReadOnlyError,
    RequestTimeoutError,
    ResponseError,
    TransportError,
)

__all__ = [
    "AuthError",
    "ClientError",
    "GPPConfigError",
    "GPPFieldUnavailableError",
    "GPPRetryableError",
    "GPPValidationError",
    "GraphQLResponseError",
    "OperationUnavailableError",
    "ReadOnlyError",
    "RequestTimeoutError",
    "ResponseError",
    "TransportError",
]


class GPPConfigError(ClientError):
    """Raised when client configuration cannot be resolved."""


class GPPFieldUnavailableError(ClientError):
    """
    Raised when a raw operation selects a field the active schema source
    does not serve.

    Parameters
    ----------
    field_name : str
        The selected field name.
    source : str
        The active schema source.
    available : tuple[str, ...]
        Schema sources where the field is available.
    """

    def __init__(
        self, field_name: str, source: str, available: tuple[str, ...]
    ) -> None:
        super().__init__(
            f"Field '{field_name}' is not available in '{source}'; "
            f"it exists in: {', '.join(available) or 'none'}."
        )
        self.field_name = field_name
        self.source = source
        self.available = available


class GPPRetryableError(ClientError):
    """Raised for transient conditions worth retrying, e.g. a background
    calculation that has not finished yet."""


class GPPValidationError(ClientError):
    """Raised when inputs fail client-side validation before any request."""
