"""
Shared fixtures. Every test runs isolated from the developer's real GPP
configuration: ``GPP_*`` environment variables are cleared and the config
file is pointed at a nonexistent path.
"""

import json
from typing import Any

import httpx
import pytest

import gpp_client2.client  # noqa: F401  (ensure package imports before patching)

GPP_ENV_VARS = (
    "GPP_ENVIRONMENT",
    "GPP_URL",
    "GPP_TOKEN",
    "GPP_PROFILE",
    "GPP_SCHEMA_SOURCE",
    "GPP_CONFIG_FILE",
)


@pytest.fixture(autouse=True)
def isolate_configuration(request, monkeypatch, tmp_path):
    """Keep offline tests away from real env vars and the user's config file.

    Live tests are exempt: they exist to talk to a real deployment, so the
    real environment (``GPP_PROFILE``, ``GPP_ENVIRONMENT``, ``GPP_TOKEN``,
    ``GPP_CONFIG_FILE``) must reach them - it is how a run or a CI job picks
    which environment to test.
    """
    if request.node.get_closest_marker("live"):
        return
    for var in GPP_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GPP_CONFIG_FILE", str(tmp_path / "nonexistent-config.toml"))


class RecordingHandler:
    """A MockTransport handler that records requests and replays responses."""

    def __init__(self, *responses: httpx.Response):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Handler received more requests than responses.")
        return self.responses.pop(0)

    @property
    def last_body(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].content)


def graphql_response(data: Any) -> httpx.Response:
    """A 200 GraphQL response wrapping ``data``."""
    return httpx.Response(200, json={"data": data})


@pytest.fixture
def make_client():
    """Factory for sync clients wired to a recording mock transport."""
    from gpp_client2 import GPPClient

    clients = []

    def factory(*responses: httpx.Response, **kwargs: Any):
        handler = RecordingHandler(*responses)
        defaults: dict[str, Any] = {
            "url": "http://odb.test",
            "schema": "development",
            "token": "test-token",
        }
        defaults.update(kwargs)
        client = GPPClient(transport=httpx.MockTransport(handler), **defaults)
        clients.append(client)
        return client, handler

    yield factory
    for client in clients:
        client.close()


@pytest.fixture
def make_async_client():
    """Factory for async clients wired to a recording mock transport."""
    from gpp_client2 import AsyncGPPClient

    def factory(*responses: httpx.Response, **kwargs: Any):
        handler = RecordingHandler(*responses)
        defaults: dict[str, Any] = {
            "url": "http://odb.test",
            "schema": "development",
            "token": "test-token",
        }
        defaults.update(kwargs)
        client = AsyncGPPClient(transport=httpx.MockTransport(handler), **defaults)
        return client, handler

    return factory
