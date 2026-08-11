"""Scheduler REST endpoint tests."""

import datetime as dt
import gzip

import httpx
import pytest

from gpp_client2 import GPPClient
from gpp_client2.errors import AuthError, ResponseError
from gpp_client2.rest import VisibilityChange
from tests.conftest import RecordingHandler


def rest_client(*responses):
    handler = RecordingHandler(*responses)
    client = GPPClient(
        url="http://odb.test",
        schema="development",
        token="t",
        transport=httpx.MockTransport(handler),
    )
    return client, handler


def test_atom_digests_posts_ids_as_lines():
    client, handler = rest_client(httpx.Response(200, text="o-1\tabc\no-2\tdef\n"))
    with client:
        tsv = client.scheduler.atom_digests(["o-1", "o-2"])
    assert tsv == "o-1\tabc\no-2\tdef\n"
    request = handler.requests[0]
    assert request.url.path == "/scheduler/atoms"
    assert request.content == b"o-1\no-2"
    assert request.headers["content-type"] == "text/plain"
    assert request.headers["authorization"] == "Bearer t"


def test_atom_digests_handles_unlabelled_gzip():
    payload = gzip.compress(b"o-1\tabc\n")
    client, _ = rest_client(
        httpx.Response(200, content=payload, headers={"Content-Type": "text/plain"})
    )
    with client:
        assert client.scheduler.atom_digests(["o-1"]) == "o-1\tabc\n"


def test_visibility_changes_parses_rows():
    client, handler = rest_client(
        httpx.Response(
            200, text="o-1\t2025-08-10T12:00:00Z\nt-2\t2025-08-10T13:00:00Z\n"
        )
    )
    with client:
        changes = client.scheduler.visibility_changes(dt.datetime(2025, 8, 10))
    assert changes == [
        VisibilityChange("o-1", dt.datetime(2025, 8, 10, 12, tzinfo=dt.UTC)),
        VisibilityChange("t-2", dt.datetime(2025, 8, 10, 13, tzinfo=dt.UTC)),
    ]
    since = handler.requests[0].url.params["since"]
    assert since.startswith("2025-08-10T00:00:00")


def test_rest_auth_error():
    client, _ = rest_client(httpx.Response(403, text="no"))
    with client, pytest.raises(AuthError):
        client.scheduler.atom_digests(["o-1"])


def test_rest_http_error():
    client, _ = rest_client(httpx.Response(400, text="bad ids"))
    with client, pytest.raises(ResponseError, match="bad ids"):
        client.scheduler.atom_digests(["o-1"])


async def test_async_scheduler_mirrors_sync():
    from gpp_client2 import AsyncGPPClient

    handler = RecordingHandler(httpx.Response(200, text="o-1\tabc\n"))
    client = AsyncGPPClient(
        url="http://odb.test",
        schema="development",
        token="t",
        transport=httpx.MockTransport(handler),
    )
    async with client:
        tsv = await client.scheduler.atom_digests(["o-1"])
    assert tsv == "o-1\tabc\n"
