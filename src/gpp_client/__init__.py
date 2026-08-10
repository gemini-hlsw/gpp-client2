"""
gpp-client: Python client for the Gemini Program Platform.

One installable package that talks to any GPP deployment - development,
staging, or production - as a runtime choice.
"""

from importlib.metadata import PackageNotFoundError, version

from gpp_client._base import UNSET, UnsetType, is_set
from gpp_client.client import AsyncGPPClient, GPPClient
from gpp_client.environments import ENVIRONMENTS, Environment
from gpp_client.errors import (
    GPPAuthError,
    GPPConfigError,
    GPPConnectionError,
    GPPError,
    GPPFieldUnavailableError,
    GPPGraphQLError,
    GPPOperationUnavailableError,
    GPPReadOnlyError,
    GPPResponseError,
    GPPTimeoutError,
)

try:
    __version__ = version("gpp-client")
except PackageNotFoundError:  # pragma: no cover - not installed
    __version__ = "0.0.0"

__all__ = [
    "ENVIRONMENTS",
    "UNSET",
    "AsyncGPPClient",
    "Environment",
    "GPPAuthError",
    "GPPClient",
    "GPPConfigError",
    "GPPConnectionError",
    "GPPError",
    "GPPFieldUnavailableError",
    "GPPGraphQLError",
    "GPPOperationUnavailableError",
    "GPPReadOnlyError",
    "GPPResponseError",
    "GPPTimeoutError",
    "UnsetType",
    "__version__",
    "is_set",
]
