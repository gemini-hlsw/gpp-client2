"""The vendored runtime: a generated client that works out of the box.

With no ``runtime_package`` configured, gqlforge must emit everything -
bases, executors, websocket transport, and a default Client/AsyncClient
- and the result must execute operations end to end over an injected
httpx transport with correct UNSET, partial-response, and read-only
semantics. The unit suites at the bottom pin the base-model and
executor-core contracts on the emitted copies.
"""

import asyncio
import copy
import datetime as dt
import json
import pickle

import httpx
import pytest
from pydantic import Field
from support import importable, make_consumer

from gqlforge.pipeline import run_generate

SCHEMA = """
type Widget {
  id: ID!
  name: String
  size: Int
}

type Query {
  widget(id: ID!): Widget
}

type Mutation {
  renameWidget(id: ID!, name: String!): Widget
}
"""

OPERATIONS = """\
query getWidgetById($id: ID!) {
  widget(id: $id) {
    id
    name
  }
}

mutation renameWidgetById($id: ID!, $name: String!) {
  renameWidget(id: $id, name: $name) {
    id
    name
  }
}
"""


@pytest.fixture
def client_module(tmp_path):
    config = make_consumer(
        tmp_path,
        "vendored_demo",
        {"main": SCHEMA},
        ["main"],
        operations=OPERATIONS,
        vendored=True,
    )
    run_generate(config)
    with importable(tmp_path, "vendored_demo") as import_module:
        yield import_module


def _transport(handler):
    return httpx.MockTransport(handler)


def _widget_response(request):
    payload = json.loads(request.content)
    assert payload["operationName"] in ("getWidgetById", "renameWidgetById")
    return httpx.Response(
        200,
        json={
            "data": {"widget": {"__typename": "Widget", "id": "w-1", "name": "gizmo"}}
        },
    )


def test_query_roundtrip_with_typed_result(client_module):
    client_mod = client_module("_generated.client")
    with client_mod.Client(
        "http://test", transport=_transport(_widget_response)
    ) as client:
        widget = client.ops.get_widget_by_id(id="w-1")
    assert widget.id == "w-1"
    assert widget.name == "gizmo"
    # `size` was not selected by the operation: UNSET, not None.
    assert repr(widget.size) == "UNSET"
    assert not widget.size


def test_async_client_mirrors_sync(client_module):
    client_mod = client_module("_generated.client")

    async def scenario():
        async with client_mod.AsyncClient(
            "http://test", transport=httpx.MockTransport(_widget_response)
        ) as client:
            return await client.ops.get_widget_by_id(id="w-1")

    widget = asyncio.run(scenario())
    assert widget.name == "gizmo"


def test_root_null_raises_and_partial_warns(client_module, caplog):
    client_mod = client_module("_generated.client")
    exceptions = client_module("_generated._exceptions")

    def all_null(request):
        return httpx.Response(
            200, json={"data": {"widget": None}, "errors": [{"message": "boom"}]}
        )

    with (
        client_mod.Client("http://test", transport=_transport(all_null)) as client,
        pytest.raises(exceptions.GraphQLResponseError),
    ):
        client.ops.get_widget_by_id(id="w-1")

    def partial(request):
        return httpx.Response(
            200,
            json={
                "data": {"widget": {"__typename": "Widget", "id": "w-1"}},
                "errors": [{"message": "background field failed"}],
            },
        )

    with (
        client_mod.Client("http://test", transport=_transport(partial)) as client,
        caplog.at_level("WARNING"),
    ):
        widget = client.ops.get_widget_by_id(id="w-1")
    assert widget.id == "w-1"
    assert any("partial data" in r.message for r in caplog.records)


def test_read_only_blocks_mutations_before_network(client_module):
    client_mod = client_module("_generated.client")
    exceptions = client_module("_generated._exceptions")

    def explode(request):  # pragma: no cover - must never be reached
        raise AssertionError("read-only client sent a request")

    with (
        client_mod.Client(
            "http://test", read_only=True, transport=_transport(explode)
        ) as client,
        pytest.raises(exceptions.ReadOnlyError),
    ):
        client.ops.rename_widget_by_id(id="w-1", name="new")


def test_raw_graphql_escape_hatch(client_module):
    client_mod = client_module("_generated.client")

    def echo(request):
        payload = json.loads(request.content)
        assert "query" in payload
        return httpx.Response(200, json={"data": {"anything": 1}})

    with client_mod.Client("http://test", transport=_transport(echo)) as client:
        data = client.graphql("query { anything }")
    assert data == {"anything": 1}


def test_auth_header_and_token_flow(client_module):
    client_mod = client_module("_generated.client")

    def check_auth(request):
        assert request.headers["Authorization"] == "Bearer tok-123"
        return httpx.Response(
            200, json={"data": {"widget": {"__typename": "Widget", "id": "w-1"}}}
        )

    with client_mod.Client(
        "http://test", token="tok-123", transport=_transport(check_auth)
    ) as client:
        client.ops.get_widget_by_id(id="w-1")


def test_requests_hit_the_endpoint_verbatim(client_module):
    """The URL given to the client is posted exactly - no trailing slash
    appended, no base-path merging (httpx base_url would do both)."""
    client_mod = client_module("_generated.client")
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            200, json={"data": {"widget": {"__typename": "Widget", "id": "w-1"}}}
        )

    with client_mod.Client("http://test/odb", transport=_transport(handler)) as client:
        client.ops.get_widget_by_id(id="w-1")
        client.graphql("query { widget { id } }")

    async def scenario():
        async with client_mod.AsyncClient(
            "http://test/odb", transport=_transport(handler)
        ) as client:
            await client.ops.get_widget_by_id(id="w-1")

    asyncio.run(scenario())
    assert seen == ["http://test/odb"] * 3


def test_specialization_via_inheritance(client_module):
    """A curated client by subclassing the vendored pieces: custom domain
    wiring plus an ExecutorCore override - the gpp-client2 migration
    path. Exceptions are simply the vendored ones."""
    client_mod = client_module("_generated.client")
    executor_mod = client_module("_generated._executor")
    domains_mod = client_module("_generated.domains")
    exceptions = client_module("_generated._exceptions")

    class ForbiddenFieldError(exceptions.ClientError):
        pass

    class MyCore(executor_mod.ExecutorCore):
        def raw_payload(self, query, variables, operation_name):
            if "secretField" in query:  # gpp-style preflight in an override
                raise ForbiddenFieldError("secretField is restricted")
            return super().raw_payload(query, variables, operation_name)

    class CuratedOps(domains_mod.Operations):
        def get_widget_name(self, id):  # curated helper on top of coverage
            return self.get_widget_by_id(id=id).name

    class MyClient(client_mod.Client):
        executor_core_class = MyCore

        def _wire_domains(self):
            self.widgets = CuratedOps(self._executor)

    with MyClient("http://test", transport=_transport(_widget_response)) as client:
        assert client.widgets.get_widget_name("w-1") == "gizmo"
        assert not hasattr(client, "ops")  # wiring fully replaced
        with pytest.raises(ForbiddenFieldError):
            client.graphql("query { secretField }")
        # And a single vendored except-clause still catches everything.
        with pytest.raises(exceptions.ClientError):
            client.graphql("query { secretField }")


# ---------------------------------------------------------------------------
# The emitted model bases: UNSET sentinel, unset-vs-null, input semantics
# ---------------------------------------------------------------------------


class TestBases:
    @pytest.fixture
    def base(self, client_module):
        return client_module("_generated._base")

    def test_unset_is_a_falsy_singleton(self, base):
        assert base.UnsetType() is base.UNSET
        assert not base.UNSET
        assert repr(base.UNSET) == "UNSET"

    def test_unset_survives_copy_and_pickle(self, base):
        assert copy.copy(base.UNSET) is base.UNSET
        assert copy.deepcopy({"k": base.UNSET})["k"] is base.UNSET
        assert pickle.loads(pickle.dumps(base.UNSET)) is base.UNSET

    def test_is_set(self, base):
        assert base.is_set(None)
        assert base.is_set(0)
        assert not base.is_set(base.UNSET)

    def _sample_model(self, base):
        class Sample(base.Model):
            name: str = base.UNSET
            nick: str | None = base.UNSET
            camel_thing: int = Field(default=base.UNSET, alias="camelThing")

        return Sample

    def test_model_distinguishes_unset_from_null(self, base):
        sample = self._sample_model(base)
        parsed = sample.model_validate({"name": "x", "nick": None})
        assert parsed.name == "x"
        assert parsed.nick is None
        assert parsed.camel_thing is base.UNSET

    def test_model_repr_shows_only_set_fields(self, base):
        sample = self._sample_model(base)
        parsed = sample.model_validate({"name": "x"})
        assert repr(parsed) == "Sample(name='x')"
        assert str(parsed) == "Sample(name='x')"

    def test_model_accepts_alias_and_python_name(self, base):
        sample = self._sample_model(base)
        assert sample.model_validate({"camelThing": 3}).camel_thing == 3
        assert sample(camel_thing=4).camel_thing == 4

    def _sample_input(self, base):
        class SampleInput(base.Input):
            name: str | None = None
            other: int | None = Field(default=None, alias="otherThing")

        return SampleInput

    def test_input_dump_omits_unset_keeps_null(self, base):
        sample = self._sample_input(base)
        assert sample(name="x").graphql_dump() == {"name": "x"}
        assert sample(name=None).graphql_dump() == {"name": None}
        assert sample().graphql_dump() == {}

    def test_input_dump_uses_aliases(self, base):
        assert self._sample_input(base)(other=1).graphql_dump() == {"otherThing": 1}

    def test_input_assignment_counts_as_set(self, base):
        value = self._sample_input(base)()
        value.name = "later"
        assert value.graphql_dump() == {"name": "later"}


# ---------------------------------------------------------------------------
# The emitted executor core: serialization, dispatch, response processing
# ---------------------------------------------------------------------------


class TestExecutorCore:
    @pytest.fixture
    def runtime(self, client_module):
        return (
            client_module("_generated._base"),
            client_module("_generated._executor"),
            client_module("_generated._exceptions"),
        )

    def test_serialize_variable_forms(self, runtime):
        base, executor, _ = runtime

        class SampleInput(base.Input):
            name: str | None = None

        serialize = executor.serialize_variable
        assert serialize(SampleInput(name="x")) == {"name": "x"}
        assert serialize(dt.datetime(2025, 8, 10, 12, 30)) == "2025-08-10T12:30:00Z"
        eastern = dt.timezone(dt.timedelta(hours=-4))
        aware = dt.datetime(2025, 8, 10, 8, 30, tzinfo=eastern)
        assert serialize(aware) == "2025-08-10T12:30:00Z"
        assert serialize(dt.date(2025, 8, 10)) == "2025-08-10"
        assert serialize({"list": [SampleInput(), 1], "plain": "x"}) == {
            "list": [{}, 1],
            "plain": "x",
        }

    def test_payload_drops_unset_variables(self, runtime):
        base, executor, _ = runtime
        payload = executor.ExecutorCore(source="main").payload(
            "getWidgetById", {"id": "w-1", "name": base.UNSET}
        )
        assert payload["variables"] == {"id": "w-1"}

    def test_unknown_operation_is_a_bug(self, runtime):
        _, executor, _ = runtime
        with pytest.raises(KeyError):
            executor.ExecutorCore(source="main").payload("noSuchOperation", {})

    def test_unavailable_operation_raises_with_availability(
        self, runtime, client_module, monkeypatch
    ):
        _, executor, exceptions = runtime
        operations = client_module("_generated.operations")
        monkeypatch.setitem(
            operations.OPERATION_TEXT, "elsewhereOnly", {"other": "query { x }"}
        )
        with pytest.raises(exceptions.OperationUnavailableError) as info:
            executor.ExecutorCore(source="main").payload("elsewhereOnly", {})
        assert info.value.operation_name == "elsewhereOnly"
        assert info.value.source == "main"
        assert info.value.available == ("other",)

    def test_raw_payload_passthrough_and_syntax_left_to_server(self, runtime):
        _, executor, _ = runtime
        core = executor.ExecutorCore(source="main")
        assert core.raw_payload("query Q { x }", {"a": 1}, "Q") == {
            "query": "query Q { x }",
            "operationName": "Q",
            "variables": {"a": 1},
        }
        assert core.raw_payload("query {{{", None, None)["query"] == "query {{{"

    def test_raw_payload_read_only_blocks_mutations(self, runtime):
        _, executor, exceptions = runtime
        core = executor.ExecutorCore(source="main", read_only=True)
        with pytest.raises(exceptions.ReadOnlyError):
            core.raw_payload("mutation M { x }", None, None)

    def test_process_maps_http_failures(self, runtime):
        _, executor, exceptions = runtime
        core = executor.ExecutorCore(source="main")
        with pytest.raises(exceptions.AuthError):
            core.process(httpx.Response(401, text="denied"))
        with pytest.raises(exceptions.ResponseError) as info:
            core.process(httpx.Response(500, text="boom"))
        assert info.value.status_code == 500
        with pytest.raises(exceptions.ResponseError, match="not JSON"):
            core.process(httpx.Response(200, text="<html>"))
