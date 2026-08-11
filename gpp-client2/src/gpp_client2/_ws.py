"""
GraphQL subscription transports, re-exported from the vendored gqlforge
runtime.

The GPP-specific WebSocket URL convention (``wss://<host>/ws``, regardless
of the HTTP path) lives in :mod:`gpp_client2.client`.
"""

from gpp_client2._generated._ws import (
    AsyncWsTransport,
    SyncWsTransport,
    WsConfig,
)

__all__ = ["AsyncWsTransport", "SyncWsTransport", "WsConfig"]
