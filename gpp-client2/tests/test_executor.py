"""Executor core unit tests: serialization, dispatch, errors."""

import datetime as dt

import httpx
import pytest

from gpp_client2 import UNSET
from gpp_client2._executor import ExecutorCore, serialize_variable
from gpp_client2._generated import operations as generated_operations
from gpp_client2._generated.enums import Existence
from gpp_client2._generated.inputs import ProgramPropertiesInput
from gpp_client2.errors import (
    GPPAuthError,
    GPPFieldUnavailableError,
    GPPGraphQLError,
    GPPOperationUnavailableError,
    GPPReadOnlyError,
    GPPResponseError,
)


def core(schema_source="development", read_only=False) -> ExecutorCore:
    return ExecutorCore(
        environment_name=schema_source,
        schema_source=schema_source,
        read_only=read_only,
    )


class TestSerializeVariable:
    def test_input_model_omits_unset(self):
        assert serialize_variable(ProgramPropertiesInput(name="x")) == {"name": "x"}

    def test_enum_becomes_value(self):
        assert serialize_variable(Existence.PRESENT) == "PRESENT"

    def test_naive_datetime_assumed_utc_with_z(self):
        value = serialize_variable(dt.datetime(2025, 8, 10, 12, 30))
        assert value == "2025-08-10T12:30:00Z"

    def test_aware_datetime_converted_to_utc(self):
        eastern = dt.timezone(dt.timedelta(hours=-4))
        value = serialize_variable(dt.datetime(2025, 8, 10, 8, 30, tzinfo=eastern))
        assert value == "2025-08-10T12:30:00Z"

    def test_date(self):
        assert serialize_variable(dt.date(2025, 8, 10)) == "2025-08-10"

    def test_nested_containers(self):
        value = serialize_variable({"list": [Existence.DELETED, 1], "plain": "x"})
        assert value == {"list": ["DELETED", 1], "plain": "x"}


class TestPayload:
    def test_selects_environment_text(self):
        payload = core("development").payload("getProgramById", {"programId": "p-1"})
        assert payload["operationName"] == "getProgramById"
        assert "program(" in payload["query"]

    def test_unset_variables_dropped(self):
        payload = core().payload(
            "getProgramById", {"programId": "p-1", "includeDeleted": UNSET}
        )
        assert payload["variables"] == {"programId": "p-1"}

    def test_unknown_operation_is_a_bug(self):
        with pytest.raises(KeyError):
            core().payload("noSuchOperation", {})

    def test_unavailable_operation_raises(self, monkeypatch):
        monkeypatch.setitem(
            generated_operations.OPERATION_TEXT,
            "getProdOnlyThing",
            {"production": "query getProdOnlyThing { x }"},
        )
        with pytest.raises(GPPOperationUnavailableError) as info:
            core("development").payload("getProdOnlyThing", {})
        assert info.value.available_in == ("production",)
        assert "development" in str(info.value)

    def test_read_only_blocks_mutations(self):
        with pytest.raises(GPPReadOnlyError):
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
        with pytest.raises(GPPReadOnlyError):
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
    def response(self, status=200, json=None, text=None):
        kwargs = {"json": json} if json is not None else {"text": text or ""}
        return httpx.Response(status, **kwargs)

    def test_data_returned(self):
        assert core().process(self.response(json={"data": {"x": 1}})) == {"x": 1}

    def test_401_is_auth_error(self):
        with pytest.raises(GPPAuthError):
            core().process(self.response(401, text="denied"))

    def test_500_is_response_error(self):
        with pytest.raises(GPPResponseError) as info:
            core().process(self.response(500, text="boom"))
        assert info.value.status_code == 500

    def test_graphql_errors_without_data_raise(self):
        with pytest.raises(GPPGraphQLError, match="bad thing"):
            core().process(
                self.response(json={"data": None, "errors": [{"message": "bad thing"}]})
            )

    def test_partial_query_data_returned_with_warning(self, caplog):
        # Observed live: one broken observation in a listing page produces a
        # field-level error alongside valid data for everything else.
        body = {
            "data": {"observations": {"hasMore": False, "matches": [{"id": "o-1"}]}},
            "errors": [{"message": "Could not generate a sequence for o-984"}],
        }
        with caplog.at_level("WARNING", logger="gpp_client2._executor"):
            data = core().process(self.response(json=body))
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
        with caplog.at_level("WARNING", logger="gpp_client2._executor"):
            data = core().process(self.response(json=body))
        assert data == body["data"]
        assert "background calculation" in caplog.text

    def test_null_root_with_errors_raises(self):
        body = {"data": {"createProgram": None}, "errors": [{"message": "denied"}]}
        with pytest.raises(GPPGraphQLError, match="denied"):
            core().process(self.response(json=body))

    def test_non_json_is_response_error(self):
        with pytest.raises(GPPResponseError, match="not JSON"):
            core().process(self.response(200, text="<html>"))
