"""Attachment REST transfer and generated queries over a mock transport."""

import httpx
import pytest

from gpp_client.errors import GPPValidationError
from tests.conftest import graphql_response


def test_upload_sends_params_and_body(make_client, tmp_path):
    client, handler = make_client(httpx.Response(200, text="a-123\n"))
    source = tmp_path / "finder.pdf"
    source.write_bytes(b"%PDF-fake")
    attachment_id = client.attachments.upload(
        "p-1",
        attachment_type="SCIENCE",
        file_name="finder.pdf",
        description="  chart  ",
        file_path=source,
    )
    assert attachment_id == "a-123"
    request = handler.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/attachment"
    assert dict(request.url.params) == {
        "programId": "p-1",
        "fileName": "finder.pdf",
        "attachmentType": "SCIENCE",
        "description": "chart",
    }
    assert request.content == b"%PDF-fake"


def test_upload_requires_exactly_one_source(make_client):
    client, _ = make_client()
    with pytest.raises(GPPValidationError, match="exactly one"):
        client.attachments.upload("p-1", attachment_type="SCIENCE", file_name="x")
    with pytest.raises(GPPValidationError, match="exactly one"):
        client.attachments.upload(
            "p-1",
            attachment_type="SCIENCE",
            file_name="x",
            file_path="/tmp/x",
            content=b"y",
        )


def test_update_and_delete(make_client):
    client, handler = make_client(httpx.Response(200), httpx.Response(204, text=""))
    client.attachments.update_by_id("a-1", file_name="new.pdf", content=b"data")
    client.attachments.delete_by_id("a-1")
    put_request, delete_request = handler.requests
    assert put_request.method == "PUT"
    assert put_request.url.path == "/attachment/a-1"
    assert dict(put_request.url.params) == {"fileName": "new.pdf"}
    assert delete_request.method == "DELETE"


def test_download_streams_presigned_url_without_auth(make_client, tmp_path):
    presigned = "http://bucket.test/signed/finder.pdf?sig=abc"

    def bare_handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"file-bytes")

    client, handler = make_client(httpx.Response(200, text=presigned + "\n"))
    # Patch the presigned fetch to a mock transport; the URL fetch itself
    # goes through the authenticated client and is handled above.
    import gpp_client.domains.attachment as attachment_module

    original = attachment_module.httpx.Client
    attachment_module.httpx.Client = lambda: original(
        transport=httpx.MockTransport(bare_handler)
    )
    try:
        path = client.attachments.download_by_id("a-1", save_to=tmp_path)
    finally:
        attachment_module.httpx.Client = original

    assert path == tmp_path / "finder.pdf"
    assert path.read_bytes() == b"file-bytes"
    assert handler.requests[0].url.path == "/attachment/url/a-1"


def test_download_refuses_overwrite(make_client, tmp_path):
    client, _ = make_client(
        httpx.Response(200, text="http://bucket.test/x/existing.bin")
    )
    (tmp_path / "existing.bin").write_bytes(b"old")
    with pytest.raises(Exception, match="already exists"):
        client.attachments.download_by_id("a-1", save_to=tmp_path)


def test_read_only_blocks_rest_writes(make_client):
    """read_only guards REST content writes exactly like GraphQL mutations."""
    from gpp_client.errors import GPPReadOnlyError

    client, handler = make_client(read_only=True)
    with pytest.raises(GPPReadOnlyError):
        client.attachments.upload(
            "p-1", attachment_type="SCIENCE", file_name="x", content=b"y"
        )
    with pytest.raises(GPPReadOnlyError):
        client.attachments.update_by_id("a-1", file_name="x", content=b"y")
    with pytest.raises(GPPReadOnlyError):
        client.attachments.delete_by_id("a-1")
    assert handler.requests == []  # nothing touched the network


async def test_read_only_blocks_rest_writes_async(make_async_client):
    from gpp_client.errors import GPPReadOnlyError

    client, handler = make_async_client(read_only=True)
    async with client:
        with pytest.raises(GPPReadOnlyError):
            await client.attachments.upload(
                "p-1", attachment_type="SCIENCE", file_name="x", content=b"y"
            )
        with pytest.raises(GPPReadOnlyError):
            await client.attachments.delete_by_id("a-1")
    assert handler.requests == []


def test_generated_queries_reachable(make_client):
    client, handler = make_client(
        graphql_response(
            {
                "program": {
                    "attachments": [
                        {"id": "a-1", "fileName": "x.pdf", "attachmentType": "SCIENCE"}
                    ]
                }
            }
        )
    )
    attachments = client.attachments.get_by_program_id("p-1")
    assert attachments[0].file_name == "x.pdf"
    assert handler.last_body["operationName"] == "getAttachmentsByProgramId"
