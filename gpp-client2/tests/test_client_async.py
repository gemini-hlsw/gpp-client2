"""Async client tests: the surface mirrors the sync client exactly."""

import httpx
import pytest

from gpp_client2 import AsyncGPPClient
from gpp_client2._generated.models import Program
from gpp_client2.errors import GPPReadOnlyError
from tests.conftest import graphql_response


async def test_get_by_id(make_async_client):
    client, handler = make_async_client(
        graphql_response({"program": {"id": "p-1", "name": "N"}})
    )
    async with client:
        program = await client.programs.get_by_id("p-1")
    assert isinstance(program, Program)
    assert program.name == "N"
    assert handler.last_body["operationName"] == "getProgramById"


async def test_get_all(make_async_client):
    client, _ = make_async_client(
        graphql_response({"programs": {"hasMore": False, "matches": []}})
    )
    async with client:
        result = await client.programs.get_all()
    assert result.matches == []


async def test_read_only(make_async_client):
    client, handler = make_async_client(read_only=True)
    async with client:
        with pytest.raises(GPPReadOnlyError):
            await client.programs.delete_by_id("p-1")
    assert handler.requests == []


async def test_raw_and_ping(make_async_client):
    client, _ = make_async_client(
        graphql_response({"x": 1}),
        graphql_response({"programs": {"matches": []}}),
    )
    async with client:
        assert await client.graphql("query Q { x }") == {"x": 1}
        assert await client.ping() == (True, None)


async def test_ping_failure():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    client = AsyncGPPClient(
        url="http://down.test",
        schema="development",
        token="t",
        transport=httpx.MockTransport(refuse),
    )
    async with client:
        ok, reason = await client.ping()
    assert ok is False
    assert "down.test" in reason
