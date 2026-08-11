"""
gpp-client2: Python client for the Gemini Program Platform.

One installable package that talks to any GPP deployment - development,
staging, or production - as a runtime choice.
"""

from importlib.metadata import PackageNotFoundError, version

from gpp_client2._base import UNSET, UnsetType, is_set
from gpp_client2.client import AsyncGPPClient, GPPClient
from gpp_client2.environments import ENVIRONMENTS, Environment
from gpp_client2.errors import (
    AuthError,
    ClientError,
    GPPConfigError,
    GPPFieldUnavailableError,
    GPPRetryableError,
    GPPValidationError,
    GraphQLResponseError,
    OperationUnavailableError,
    ReadOnlyError,
    RequestTimeoutError,
    ResponseError,
    TransportError,
)

try:
    __version__ = version("gpp-client2")
except PackageNotFoundError:  # pragma: no cover - not installed
    __version__ = "0.0.0"

__all__ = [
    "ENVIRONMENTS",
    "UNSET",
    "AsyncGPPClient",
    "AuthError",
    "ClientError",
    "Environment",
    "GPPClient",
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
    "UnsetType",
    "__version__",
    "is_set",
]
