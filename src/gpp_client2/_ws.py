"""
GraphQL subscriptions over the ``graphql-transport-ws`` protocol.

The message handling is transport-free (:class:`_Protocol`); the two
transports add only the actual WebSocket I/O - ``websockets`` ships both a
sync and an asyncio client - so sync and async subscription behavior cannot
drift. Each subscription call opens its own connection: one socket, one
``subscribe``, closed when iteration ends.

Event payloads flow through the same root-null partial-response semantics as
HTTP responses (see :meth:`gpp_client2._executor.ExecutorCore.process_body`).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect as _async_connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect as _sync_connect
from websockets.typing import Subprotocol

from gpp_client2.errors import (
    GPPAuthError,
    GPPConnectionError,
    GPPError,
    GPPGraphQLError,
    GPPTimeoutError,
)

__all__ = ["AsyncWsTransport", "SyncWsTransport", "WsConfig", "get_ws_url"]

GRAPHQL_WS_SUBPROTOCOL = "graphql-transport-ws"
WS_PATH = "/ws"

_SUB_ID = "1"  # one subscription per connection, so a constant id suffices


def get_ws_url(base_url: str) -> str:
    """WebSocket endpoint for a deployment base URL, e.g. ``wss://host/ws``."""
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, WS_PATH, "", ""))


@dataclass(frozen=True)
class WsConfig:
    """
    Connection settings for the subscription transport.

    Parameters
    ----------
    url : str
        The ``ws(s)://`` endpoint.
    token : str
        GPP API token, sent in the upgrade request and the
        ``connection_init`` payload.
    connect_timeout : float
        Seconds allowed for the handshake up to ``connection_ack``.
    """

    url: str
    token: str
    connect_timeout: float


class SupportsProcessBody(Protocol):
    """The slice of ``ExecutorCore`` the protocol layer needs."""

    def process_body(self, body: dict[str, Any]) -> Any: ...


class _Protocol:
    """Sans-I/O ``graphql-transport-ws`` message handling for one stream."""

    def __init__(self, core: SupportsProcessBody, token: str) -> None:
        self._core = core
        self._token = token

    def init_message(self) -> str:
        return json.dumps(
            {
                "type": "connection_init",
                "payload": {"Authorization": f"Bearer {self._token}"},
            }
        )

    def subscribe_message(self, payload: dict[str, Any]) -> str:
        return json.dumps({"type": "subscribe", "id": _SUB_ID, "payload": payload})

    def handle(self, raw: str | bytes) -> tuple[str, Any]:
        """
        Interpret one server message.

        Returns
        -------
        tuple[str, Any]
            An ``(action, value)`` pair: ``("ack", None)``,
            ``("event", data)``, ``("complete", None)``, ``("reply", text)``
            for a message that must be sent back, or ``("ignore", None)``.

        Raises
        ------
        GPPGraphQLError
            For an ``error`` message, or an event whose every root field is
            null.
        """
        message = json.loads(raw)
        kind = message.get("type")
        if kind == "connection_ack":
            return ("ack", None)
        if kind == "ping":
            return ("reply", json.dumps({"type": "pong"}))
        if message.get("id") != _SUB_ID:
            return ("ignore", None)
        if kind == "next":
            return ("event", self._core.process_body(message.get("payload") or {}))
        if kind == "error":
            payload = message.get("payload")
            errors = payload if isinstance(payload, list) else [payload or {}]
            raise GPPGraphQLError(errors)
        if kind == "complete":
            return ("complete", None)
        return ("ignore", None)


def _map_ws_error(exc: Exception, url: str) -> Exception:
    """Translate WebSocket failures into client exceptions."""
    if isinstance(exc, InvalidStatus):
        code = exc.response.status_code
        if code in (401, 403):
            return GPPAuthError(
                f"Authentication failed during the WebSocket handshake with "
                f"{url} (HTTP {code}). Check your token."
            )
        return GPPConnectionError(
            f"WebSocket handshake with {url} failed: HTTP {code}."
        )
    if isinstance(exc, ConnectionClosed):
        close_code = exc.rcvd.code if exc.rcvd is not None else None
        if close_code in (4401, 4403):
            return GPPAuthError(
                f"The server closed the subscription as unauthorized "
                f"(close code {close_code})."
            )
        suffix = f" (close code {close_code})" if close_code is not None else ""
        return GPPConnectionError(
            f"The subscription connection to {url} closed before the server "
            f"completed it{suffix}."
        )
    if isinstance(exc, TimeoutError):
        return GPPTimeoutError(f"Connecting to {url} timed out: {exc}")
    return GPPConnectionError(f"Could not reach {url}: {exc}")


class SyncWsTransport:
    """Runs subscriptions over ``websockets``' sync client."""

    def __init__(self, config: WsConfig, core: SupportsProcessBody) -> None:
        self._config = config
        self._core = core

    def stream(self, payload: dict[str, Any]) -> Iterator[Any]:
        """Connect, subscribe with ``payload``, and yield raw event data."""
        protocol = _Protocol(self._core, self._config.token)
        try:
            with _sync_connect(
                self._config.url,
                subprotocols=[Subprotocol(GRAPHQL_WS_SUBPROTOCOL)],
                additional_headers={"Authorization": f"Bearer {self._config.token}"},
                open_timeout=self._config.connect_timeout,
            ) as connection:
                connection.send(protocol.init_message())
                while True:
                    raw = connection.recv(timeout=self._config.connect_timeout)
                    action, value = protocol.handle(raw)
                    if action == "ack":
                        break
                    if action == "reply":
                        connection.send(value)
                connection.send(protocol.subscribe_message(payload))
                while True:
                    action, value = protocol.handle(connection.recv())
                    if action == "event":
                        yield value
                    elif action == "reply":
                        connection.send(value)
                    elif action == "complete":
                        return
        except GPPError:
            raise
        except Exception as exc:
            raise _map_ws_error(exc, self._config.url) from exc


class AsyncWsTransport:
    """Runs subscriptions over ``websockets``' asyncio client."""

    def __init__(self, config: WsConfig, core: SupportsProcessBody) -> None:
        self._config = config
        self._core = core

    async def stream(self, payload: dict[str, Any]) -> AsyncIterator[Any]:
        """Connect, subscribe with ``payload``, and yield raw event data."""
        protocol = _Protocol(self._core, self._config.token)
        try:
            async with _async_connect(
                self._config.url,
                subprotocols=[Subprotocol(GRAPHQL_WS_SUBPROTOCOL)],
                additional_headers={"Authorization": f"Bearer {self._config.token}"},
                open_timeout=self._config.connect_timeout,
            ) as connection:
                await connection.send(protocol.init_message())
                async with asyncio.timeout(self._config.connect_timeout):
                    while True:
                        action, value = protocol.handle(await connection.recv())
                        if action == "ack":
                            break
                        if action == "reply":
                            await connection.send(value)
                await connection.send(protocol.subscribe_message(payload))
                while True:
                    action, value = protocol.handle(await connection.recv())
                    if action == "event":
                        yield value
                    elif action == "reply":
                        await connection.send(value)
                    elif action == "complete":
                        return
        except GPPError:
            raise
        except Exception as exc:
            raise _map_ws_error(exc, self._config.url) from exc
