"""
Operation execution shared by the sync and async clients.

The core is transport-free: it turns an operation name plus Python variables
into a JSON payload (choosing the query text generated for the active
environment) and turns an HTTP response into a ``data`` dict, mapping
failures onto the client's exception types. The two executors add only the
actual HTTP call, so sync and async behavior cannot drift.
"""

from __future__ import annotations

import datetime as _dt
import logging
from collections.abc import AsyncIterator, Iterator
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel

from gpp_client._base import GPPInput, UnsetType
from gpp_client._ws import AsyncWsTransport, SyncWsTransport
from gpp_client.errors import (
    GPPAuthError,
    GPPConnectionError,
    GPPFieldUnavailableError,
    GPPGraphQLError,
    GPPOperationUnavailableError,
    GPPReadOnlyError,
    GPPResponseError,
    GPPTimeoutError,
)

__all__ = ["AsyncExecutor", "ExecutorCore", "SyncExecutor"]

logger = logging.getLogger(__name__)

GRAPHQL_PATH = "/odb"


def serialize_variable(value: Any) -> Any:
    """Convert a Python value into its GraphQL variable JSON form."""
    if isinstance(value, GPPInput):
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
    Environment-aware payload construction and response processing.

    Parameters
    ----------
    environment_name : str
        Human-readable environment name used in error messages.
    schema_source : str
        Committed schema source whose query text this client sends.
    read_only : bool
        When ``True``, refuse to execute mutations.
    """

    def __init__(
        self, *, environment_name: str, schema_source: str, read_only: bool
    ) -> None:
        self.environment_name = environment_name
        self.schema_source = schema_source
        self.read_only = read_only

    def payload(self, operation_name: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Build the JSON payload for a generated operation."""
        from gpp_client._generated.operations import OPERATION_KIND, OPERATION_TEXT

        texts = OPERATION_TEXT.get(operation_name)
        if texts is None:
            raise KeyError(f"Unknown generated operation '{operation_name}'.")
        if self.schema_source not in texts:
            raise GPPOperationUnavailableError(
                operation_name, self.environment_name, tuple(texts)
            )
        if self.read_only and OPERATION_KIND.get(operation_name) == "mutation":
            raise GPPReadOnlyError(
                f"'{operation_name}' is a mutation and this client is read-only."
            )
        return {
            "query": texts[self.schema_source],
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

        Pre-flights what can be checked without a schema: mutations against a
        read-only client, and selected field names whose availability is
        restricted and unambiguous.
        """
        from gpp_client._generated.operations import RESTRICTED_FIELD_NAMES

        try:
            from graphql.language.visitor import Visitor

            from graphql import (
                FieldNode,
                OperationDefinitionNode,
                OperationType,
                parse,
                visit,
            )

            document = parse(query)
        except Exception:
            document = None  # let the server report the syntax error

        is_mutation = False
        if document is not None:
            is_mutation = any(
                isinstance(d, OperationDefinitionNode)
                and d.operation is OperationType.MUTATION
                for d in document.definitions
            )
            if self.read_only and is_mutation:
                raise GPPReadOnlyError(
                    "This client is read-only and the operation contains a mutation."
                )

            schema_source = self.schema_source
            violations: list[tuple[str, tuple[str, ...]]] = []

            class _RestrictedFieldVisitor(Visitor):
                def enter_field(self, node: FieldNode, *args: Any) -> None:
                    availability = RESTRICTED_FIELD_NAMES.get(node.name.value)
                    if availability is not None and schema_source not in availability:
                        violations.append((node.name.value, availability))

            visit(document, _RestrictedFieldVisitor())
            if violations:
                field_name, availability = violations[0]
                raise GPPFieldUnavailableError(
                    field_name, self.environment_name, availability
                )

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
        """
        Map an HTTP response onto ``data`` or a typed exception.

        Partial responses follow GraphQL semantics: errors bubble nulls up to
        the nearest nullable field, so the operation itself failed exactly
        when every root field is null - that raises. When the root payload
        survived, nested field errors (a broken observation in a listing
        page, a background calculation that has not run yet for a just-created
        observation) null out only their own subtree; the data is returned
        and the errors are logged as a warning. For mutations the root field
        is the write itself, so a surviving root means the write happened.
        """
        if response.status_code in (401, 403):
            raise GPPAuthError(
                f"Authentication failed (HTTP {response.status_code}). Check "
                f"your token for '{self.environment_name}'."
            )
        if response.status_code >= 400:
            raise GPPResponseError(response.status_code, response.text[:500])
        try:
            body = response.json()
        except ValueError as exc:
            raise GPPResponseError(
                response.status_code, f"Response is not JSON: {response.text[:200]}"
            ) from exc
        return self.process_body(body)

    def process_body(self, body: dict[str, Any]) -> Any:
        """
        Apply root-null semantics to a GraphQL result body.

        Shared by HTTP responses and subscription events: each carries the
        same ``{"data": ..., "errors": ...}`` shape.
        """
        errors = body.get("errors")
        data = body.get("data")
        if errors:
            root_failed = data is None or all(value is None for value in data.values())
            if root_failed:
                raise GPPGraphQLError(errors)
            logger.warning(
                "GraphQL returned partial data with %d error(s): %s",
                len(errors),
                "; ".join(str(e.get("message", e)) for e in errors[:3]),
            )
        return data


def _map_transport_error(exc: httpx.HTTPError, url: str) -> Exception:
    """Translate httpx transport errors into client exceptions."""
    if isinstance(exc, httpx.TimeoutException):
        return GPPTimeoutError(f"Request to {url} timed out: {exc}")
    return GPPConnectionError(f"Could not reach {url}: {exc}")


class SyncExecutor:
    """Executes operations over an ``httpx.Client``."""

    def __init__(
        self,
        http: httpx.Client,
        core: ExecutorCore,
        ws: SyncWsTransport | None = None,
    ) -> None:
        self._http = http
        self.core = core
        self._ws = ws

    def run(self, operation_name: str, variables: dict[str, Any]) -> Any:
        """Execute a generated operation and return the ``data`` dict."""
        return self._post(self.core.payload(operation_name, variables))

    def stream(self, operation_name: str, variables: dict[str, Any]) -> Iterator[Any]:
        """
        Open a subscription and return its raw event iterator.

        Availability and the payload are resolved eagerly, so environment
        errors raise at the call site rather than mid-iteration.
        """
        payload = self.core.payload(operation_name, variables)
        if self._ws is None:
            raise GPPConnectionError(
                "This client was built without a WebSocket transport."
            )
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
            response = self._http.post(GRAPHQL_PATH, json=payload)
        except httpx.HTTPError as exc:
            raise _map_transport_error(exc, str(self._http.base_url)) from exc
        return self.core.process(response)


class AsyncExecutor:
    """Executes operations over an ``httpx.AsyncClient``."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        core: ExecutorCore,
        ws: AsyncWsTransport | None = None,
    ) -> None:
        self._http = http
        self.core = core
        self._ws = ws

    async def run(self, operation_name: str, variables: dict[str, Any]) -> Any:
        """Execute a generated operation and return the ``data`` dict."""
        return await self._post(self.core.payload(operation_name, variables))

    def stream(
        self, operation_name: str, variables: dict[str, Any]
    ) -> AsyncIterator[Any]:
        """
        Open a subscription and return its raw event iterator.

        Availability and the payload are resolved eagerly, so environment
        errors raise at the call site rather than mid-iteration.
        """
        payload = self.core.payload(operation_name, variables)
        if self._ws is None:
            raise GPPConnectionError(
                "This client was built without a WebSocket transport."
            )
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
            response = await self._http.post(GRAPHQL_PATH, json=payload)
        except httpx.HTTPError as exc:
            raise _map_transport_error(exc, str(self._http.base_url)) from exc
        return self.core.process(response)
