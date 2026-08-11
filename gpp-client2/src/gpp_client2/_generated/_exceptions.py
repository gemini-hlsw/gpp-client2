# Vendored by `gqlforge generate`. DO NOT EDIT.
# mypy: ignore-errors
"""
Exception hierarchy for the generated client.

One base, ``ClientError``, so a single ``except`` catches everything the
client raises; subclasses say whose problem it is.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

__all__ = [
    "AuthError",
    "ClientError",
    "GraphQLResponseError",
    "OperationUnavailableError",
    "ReadOnlyError",
    "RequestTimeoutError",
    "ResponseError",
    "TransportError",
]


class ClientError(Exception):
    """Base class for every error the generated client raises."""


class TransportError(ClientError):
    """The server could not be reached, or the connection dropped."""


class RequestTimeoutError(TransportError):
    """A request or connect timed out."""


class AuthError(ClientError):
    """The server rejected the credentials."""


class ResponseError(ClientError):
    """The server returned a non-success HTTP status."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"HTTP {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class GraphQLResponseError(ClientError):
    """Every root field of a GraphQL response was null."""

    def __init__(self, errors: Sequence[dict[str, Any]]) -> None:
        messages = "; ".join(str(e.get("message", e)) for e in errors[:3])
        super().__init__(f"GraphQL request failed: {messages}")
        self.errors = list(errors)


class OperationUnavailableError(ClientError):
    """The operation does not exist in the active schema source."""

    def __init__(
        self, operation_name: str, source: str, available: tuple[str, ...]
    ) -> None:
        super().__init__(
            f"Operation '{operation_name}' is not available in '{source}'; "
            f"it exists in: {', '.join(available)}."
        )
        self.operation_name = operation_name
        self.source = source
        self.available = available


class ReadOnlyError(ClientError):
    """A mutation was attempted on a read-only client."""
