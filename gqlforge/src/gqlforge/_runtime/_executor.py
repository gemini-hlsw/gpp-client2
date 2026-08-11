"""
Operation execution shared by the sync and async clients.

The core is transport-free: it turns an operation name plus Python
variables into a JSON payload (choosing the query text generated for the
active schema source) and turns an HTTP response into a ``data`` dict,
mapping failures onto the client's exception types. The two executors
add only the actual HTTP call, so sync and async behavior cannot drift.
"""

from __future__ import annotations

import datetime as _dt
import logging
from collections.abc import AsyncIterator, Iterator
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel

from ._base import Input, UnsetType
from ._exceptions import (
    AuthError,
    GraphQLResponseError,
    OperationUnavailableError,
    ReadOnlyError,
    RequestTimeoutError,
    ResponseError,
    TransportError,
)
from ._ws import AsyncWsTransport, SyncWsTransport

__all__ = ["AsyncExecutor", "ExecutorCore", "SyncExecutor"]

logger = logging.getLogger(__name__)


def serialize_variable(value: Any) -> Any:
    """Convert a Python value into its GraphQL variable JSON form."""
    if isinstance(value, Input):
        return value.graphql_dump()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=_dt.UTC)
        return value.astimezone(_dt.UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [serialize_variable(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize_variable(v) for k, v in value.items()}
    return value


class ExecutorCore:
    """
    Source-aware payload construction and response processing.

    Parameters
    ----------
    source : str
        Schema source whose generated query text this client sends.
    read_only : bool
        When ``True``, refuse to execute mutations.
    """

    def __init__(self, *, source: str, read_only: bool = False) -> None:
        self.source = source
        self.read_only = read_only

    def payload(self, operation_name: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Build the JSON payload for a generated operation."""
        from .operations import OPERATION_KIND, OPERATION_TEXT

        texts = OPERATION_TEXT.get(operation_name)
        if texts is None:
            raise KeyError(f"Unknown generated operation '{operation_name}'.")
        if self.source not in texts:
            raise OperationUnavailableError(operation_name, self.source, tuple(texts))
        if self.read_only and OPERATION_KIND.get(operation_name) == "mutation":
            raise ReadOnlyError(
                f"'{operation_name}' is a mutation and this client is read-only."
            )
        return {
            "query": texts[self.source],
            "operationName": operation_name,
            "variables": {
                name: serialize_variable(value)
                for name, value in variables.items()
                if not isinstance(value, UnsetType)
            },
        }

    def raw_payload(
        self,
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
    ) -> dict[str, Any]:
        """
        Build the payload for a raw, user-written operation.

        When graphql-core is importable, pre-flights mutations against a
        read-only client; otherwise the server is the judge.
        """
        if self.read_only:
            try:
                from graphql import OperationDefinitionNode, OperationType, parse

                document = parse(query)
                if any(
                    isinstance(d, OperationDefinitionNode)
                    and d.operation is OperationType.MUTATION
                    for d in document.definitions
                ):
                    raise ReadOnlyError(
                        "This client is read-only and the operation contains "
                        "a mutation."
                    )
            except ReadOnlyError:
                raise
            except Exception:
                pass

        payload: dict[str, Any] = {"query": query}
        if operation_name is not None:
            payload["operationName"] = operation_name
        if variables is not None:
            payload["variables"] = {
                name: serialize_variable(value)
                for name, value in variables.items()
                if not isinstance(value, UnsetType)
            }
        return payload

    def process(self, response: httpx.Response) -> Any:
        """Map an HTTP response onto ``data`` or a typed exception."""
        if response.status_code in (401, 403):
            raise AuthError(
                f"Authentication failed (HTTP {response.status_code}). "
                "Check your token."
            )
        if response.status_code >= 400:
            raise ResponseError(response.status_code, response.text[:500])
        try:
            body = response.json()
        except ValueError as exc:
            raise ResponseError(
                response.status_code,
                f"Response is not JSON: {response.text[:200]}",
            ) from exc
        return self.process_body(body)

    def process_body(self, body: dict[str, Any]) -> Any:
        """
        Apply root-null semantics to a GraphQL result body.

        Errors bubble nulls up to the nearest nullable field, so the
        operation itself failed exactly when every root field is null -
        that raises. When the root payload survived, nested field errors
        null out only their own subtree; the data is returned and the
        errors are logged as a warning. Shared by HTTP responses and
        subscription events.
        """
        errors = body.get("errors")
        data = body.get("data")
        if errors:
            root_failed = data is None or all(value is None for value in data.values())
            if root_failed:
                raise GraphQLResponseError(errors)
            logger.warning(
                "GraphQL returned partial data with %d error(s): %s",
                len(errors),
                "; ".join(str(e.get("message", e)) for e in errors[:3]),
            )
        return data


def _map_transport_error(exc: httpx.HTTPError, url: str) -> Exception:
    """Translate httpx transport errors into client exceptions."""
    if isinstance(exc, httpx.TimeoutException):
        return RequestTimeoutError(f"Request to {url} timed out: {exc}")
    return TransportError(f"Could not reach {url}: {exc}")


class SyncExecutor:
    """
    Executes operations over an ``httpx.Client``.

    ``url`` is the exact endpoint posted to; when empty, requests fall back
    to the client's ``base_url`` (which httpx normalizes with a trailing
    slash - pass ``url`` to hit the endpoint verbatim).
    """

    def __init__(
        self,
        http: httpx.Client,
        core: ExecutorCore,
        ws: SyncWsTransport | None = None,
        url: str = "",
    ) -> None:
        self._http = http
        self.core = core
        self._ws = ws
        self._url = url

    def run(self, operation_name: str, variables: dict[str, Any]) -> Any:
        """Execute a generated operation and return the ``data`` dict."""
        return self._post(self.core.payload(operation_name, variables))

    def stream(self, operation_name: str, variables: dict[str, Any]) -> Iterator[Any]:
        """Open a subscription and return its raw event iterator."""
        payload = self.core.payload(operation_name, variables)
        if self._ws is None:
            raise TransportError("This client was built without a WebSocket transport.")
        return self._ws.stream(payload)

    def run_raw(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> Any:
        """Execute a raw operation and return the ``data`` dict."""
        return self._post(self.core.raw_payload(query, variables, operation_name))

    def _post(self, payload: dict[str, Any]) -> Any:
        try:
            response = self._http.post(self._url, json=payload)
        except httpx.HTTPError as exc:
            raise _map_transport_error(
                exc, self._url or str(self._http.base_url)
            ) from exc
        return self.core.process(response)


class AsyncExecutor:
    """
    Executes operations over an ``httpx.AsyncClient``.

    ``url`` is the exact endpoint posted to; when empty, requests fall back
    to the client's ``base_url`` (which httpx normalizes with a trailing
    slash - pass ``url`` to hit the endpoint verbatim).
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        core: ExecutorCore,
        ws: AsyncWsTransport | None = None,
        url: str = "",
    ) -> None:
        self._http = http
        self.core = core
        self._ws = ws
        self._url = url

    async def run(self, operation_name: str, variables: dict[str, Any]) -> Any:
        """Execute a generated operation and return the ``data`` dict."""
        return await self._post(self.core.payload(operation_name, variables))

    def stream(
        self, operation_name: str, variables: dict[str, Any]
    ) -> AsyncIterator[Any]:
        """Open a subscription and return its raw event iterator."""
        payload = self.core.payload(operation_name, variables)
        if self._ws is None:
            raise TransportError("This client was built without a WebSocket transport.")
        return self._ws.stream(payload)

    async def run_raw(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> Any:
        """Execute a raw operation and return the ``data`` dict."""
        return await self._post(self.core.raw_payload(query, variables, operation_name))

    async def _post(self, payload: dict[str, Any]) -> Any:
        try:
            response = await self._http.post(self._url, json=payload)
        except httpx.HTTPError as exc:
            raise _map_transport_error(
                exc, self._url or str(self._http.base_url)
            ) from exc
        return self.core.process(response)
