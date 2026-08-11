"""
The GPP executor-core specialization and its wiring to the real generated
operation map.

Generic executor behavior (variable serialization, HTTP error mapping,
read-only and partial-response semantics) belongs to the vendored gqlforge
runtime and is pinned in gqlforge's ``tests/test_runtime.py``; here we cover
what GPP adds on top - the restricted-field preflight - and that the
vendored core drives this project's actual operations.
"""

import httpx
import pytest

from gpp_client2._generated import operations as generated_operations
from gpp_client2.client import GPPExecutorCore
from gpp_client2.errors import (
    GPPFieldUnavailableError,
    GraphQLResponseError,
    OperationUnavailableError,
    ReadOnlyError,
)


def core(source="development", read_only=False) -> GPPExecutorCore:
    return GPPExecutorCore(source=source, read_only=read_only)


class TestPayload:
    def test_selects_environment_text(self):
        payload = core("development").payload("getProgramById", {"programId": "p-1"})
        assert payload["operationName"] == "getProgramById"
        assert "program(" in payload["query"]

    def test_unavailable_operation_raises(self, monkeypatch):
        monkeypatch.setitem(
            generated_operations.OPERATION_TEXT,
            "getProdOnlyThing",
            {"production": "query getProdOnlyThing { x }"},
        )
        with pytest.raises(OperationUnavailableError) as info:
            core("development").payload("getProdOnlyThing", {})
        assert info.value.available == ("production",)
        assert "development" in str(info.value)

    def test_read_only_blocks_mutations(self):
        with pytest.raises(ReadOnlyError):
            core(read_only=True).payload("createProgram", {})

    def test_read_only_allows_queries(self):
        assert core(read_only=True).payload("getPrograms", {})


class TestRawPayload:
    def test_passthrough(self):
        payload = core().raw_payload("query Q { x }", {"a": 1}, "Q")
        assert payload == {
            "query": "query Q { x }",
            "operationName": "Q",
            "variables": {"a": 1},
        }

    def test_read_only_blocks_raw_mutations(self):
        with pytest.raises(ReadOnlyError):
            core(read_only=True).raw_payload("mutation M { x }", None, None)

    def test_restricted_field_preflight(self):
        # gnirsImaging exists only in the development schema, and codegen
        # derived that automatically.
        assert "gnirsImaging" in generated_operations.RESTRICTED_FIELD_NAMES
        with pytest.raises(GPPFieldUnavailableError, match="gnirsImaging"):
            core("production").raw_payload(
                "query Q { observation { observingMode { gnirsImaging { camera } } } }",
                None,
                None,
            )

    def test_restricted_field_allowed_where_available(self):
        assert core("development").raw_payload(
            "query Q { observation { observingMode { gnirsImaging { camera } } } }",
            None,
            None,
        )

    def test_syntax_errors_left_to_server(self):
        assert core().raw_payload("query {{{", None, None)["query"] == "query {{{"


class TestProcess:
    """Partial-response semantics against bodies observed live on GPP."""

    def response(self, json):
        return httpx.Response(200, json=json)

    def test_partial_query_data_returned_with_warning(self, caplog):
        # Observed live: one broken observation in a listing page produces a
        # field-level error alongside valid data for everything else.
        body = {
            "data": {"observations": {"hasMore": False, "matches": [{"id": "o-1"}]}},
            "errors": [{"message": "Could not generate a sequence for o-984"}],
        }
        with caplog.at_level("WARNING", logger="gpp_client2._generated._executor"):
            data = core().process(self.response(body))
        assert data == body["data"]
        assert "o-984" in caplog.text

    def test_partial_mutation_with_surviving_root_returns_data(self, caplog):
        # Observed live: createObservation succeeds but the response selects
        # calculated fields whose background job has not run yet.
        body = {
            "data": {"createObservation": {"observation": {"id": "o-1"}}},
            "errors": [
                {"message": "The background calculation has not (yet) produced"}
            ],
        }
        with caplog.at_level("WARNING", logger="gpp_client2._generated._executor"):
            data = core().process(self.response(body))
        assert data == body["data"]
        assert "background calculation" in caplog.text

    def test_null_root_with_errors_raises(self):
        body = {"data": {"createProgram": None}, "errors": [{"message": "denied"}]}
        with pytest.raises(GraphQLResponseError, match="denied"):
            core().process(self.response(body))
