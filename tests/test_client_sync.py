"""Sync client end-to-end tests over a mock transport."""

import httpx
import pytest

from gpp_client2 import UNSET, GPPClient
from gpp_client2._generated.enums import Existence
from gpp_client2._generated.inputs import ProgramPropertiesInput
from gpp_client2._generated.models import Program, ProgramSelectResult
from gpp_client2.errors import (
    GPPConnectionError,
    GPPGraphQLError,
    GPPReadOnlyError,
)
from tests.conftest import graphql_response


def test_get_by_id_returns_typed_model(make_client):
    client, handler = make_client(
        graphql_response(
            {"program": {"id": "p-1", "name": "N", "existence": "PRESENT"}}
        )
    )
    program = client.programs.get_by_id("p-1")
    assert isinstance(program, Program)
    assert program.existence is Existence.PRESENT
    assert program.description is UNSET
    body = handler.last_body
    assert body["operationName"] == "getProgramById"
    assert body["variables"] == {"programId": "p-1"}
    assert handler.requests[-1].headers["authorization"] == "Bearer test-token"
    assert handler.requests[-1].url.path == "/odb"


def test_nullable_payload_returns_none(make_client):
    client, _ = make_client(graphql_response({"program": None}))
    assert client.programs.get_by_id("p-404") is None


def test_get_all_returns_select_result(make_client):
    client, handler = make_client(
        graphql_response({"programs": {"hasMore": True, "matches": [{"id": "p-1"}]}})
    )
    result = client.programs.get_all(limit=1)
    assert isinstance(result, ProgramSelectResult)
    assert result.has_more is True
    assert result.matches[0].id == "p-1"
    assert handler.last_body["variables"] == {"limit": 1}


def test_create_unwraps_result_wrapper(make_client):
    client, handler = make_client(
        graphql_response({"createProgram": {"program": {"id": "p-9"}}})
    )
    program = client.programs.create(properties=ProgramPropertiesInput(name="X"))
    assert isinstance(program, Program)
    assert program.id == "p-9"
    assert handler.last_body["variables"] == {"properties": {"name": "X"}}


def test_update_by_id_serializes_input(make_client):
    client, handler = make_client(
        graphql_response(
            {"updatePrograms": {"hasMore": False, "programs": [{"id": "p-1"}]}}
        )
    )
    result = client.programs.update_by_id(
        "p-1", properties=ProgramPropertiesInput(description=None)
    )
    assert result.programs[0].id == "p-1"
    assert handler.last_body["variables"] == {
        "programId": "p-1",
        "properties": {"description": None},
    }


def test_read_only_client_blocks_mutations(make_client):
    client, handler = make_client(read_only=True)
    with pytest.raises(GPPReadOnlyError):
        client.programs.delete_by_id("p-1")
    assert handler.requests == []  # nothing hit the network


def test_graphql_errors_surface(make_client):
    client, _ = make_client(httpx.Response(200, json={"errors": [{"message": "nope"}]}))
    with pytest.raises(GPPGraphQLError, match="nope"):
        client.programs.get_by_id("p-1")


def test_raw_graphql_escape_hatch(make_client):
    client, handler = make_client(graphql_response({"whatever": 1}))
    data = client.graphql("query Q { whatever }", operation_name="Q")
    assert data == {"whatever": 1}
    assert handler.last_body["query"] == "query Q { whatever }"


def test_ping_success_and_failure(make_client):
    client, _ = make_client(graphql_response({"programs": {"matches": []}}))
    assert client.ping() == (True, None)

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    bad = GPPClient(
        url="http://down.test",
        schema="development",
        token="t",
        transport=httpx.MockTransport(refuse),
    )
    ok, reason = bad.ping()
    assert ok is False and "down.test" in reason
    bad.close()


def test_connection_error_mapping(make_client):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    client = GPPClient(
        url="http://down.test",
        schema="development",
        token="t",
        transport=httpx.MockTransport(refuse),
    )
    with pytest.raises(GPPConnectionError):
        client.programs.get_by_id("p-1")
    client.close()


def test_context_manager_and_repr(make_client):
    with GPPClient(
        url="http://odb.test",
        schema="production",
        token="t",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    ) as client:
        assert client.environment == "custom"
        assert "schema_source='production'" in repr(client)


def test_supports(make_client):
    client, _ = make_client()  # development
    assert client.supports("ObservingMode.gnirsImaging")
    assert client.supports("getProgramById")
    assert client.supports("programs.get_by_id")

    prod = GPPClient(
        url="http://odb.test",
        schema="production",
        token="t",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    assert not prod.supports("ObservingMode.gnirsImaging")
    assert prod.supports("getProgramById")
    prod.close()
