"""
Subscriptions: the graphql-transport-ws transports (sync and async) against
an in-process scripted server, and environment coverage - every subscription
must be available in development, staging, AND production.
"""

import asyncio
import http
import json
import threading

import pytest
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from websockets.typing import Subprotocol

from gpp_client import AsyncGPPClient, GPPClient
from gpp_client._generated.models import ObscalcUpdate, ProgramEdit
from gpp_client._generated.operations import OPERATION_KIND, OPERATION_TEXT
from gpp_client._ws import get_ws_url
from gpp_client.environments import ENVIRONMENTS
from gpp_client.errors import (
    GPPAuthError,
    GPPConnectionError,
    GPPGraphQLError,
    GPPOperationUnavailableError,
)

SUBSCRIPTION_OPERATIONS = sorted(
    name for name, kind in OPERATION_KIND.items() if kind == "subscription"
)

PROGRAM_EVENT = {
    "data": {
        "programEdit": {
            "editType": "UPDATED",
            "value": {"id": "p-1", "name": "Watched"},
        }
    }
}


class ScriptedWSServer:
    """
    In-process graphql-transport-ws server driven by an action script.

    Runs its own asyncio loop in a daemon thread so sync-client tests and
    pytest-asyncio tests both talk to it over a real socket. Actions:
    ``("next", payload)``, ``("error", payload)``, ``("ping",)``,
    ``("complete",)``, ``("close_abrupt",)``.
    """

    def __init__(self, script=(), *, accept_auth=True, http_status=None):
        self.script = list(script)
        self.accept_auth = accept_auth
        self.http_status = http_status
        self.init_payload = None
        self.subscribe_payload = None
        self.pongs = 0
        self.port = None
        self._ready = threading.Event()
        self._loop = None
        self._stop = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(5), "scripted ws server failed to start"
        return self

    def stop(self):
        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: self._stop.done() or self._stop.set_result(None)
            )
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _run(self):
        asyncio.run(self._main())

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        self._stop = self._loop.create_future()

        def process_request(connection, request):
            if self.http_status is not None:
                return connection.respond(
                    http.HTTPStatus(self.http_status), "rejected\n"
                )
            return None

        async with serve(
            self._handler,
            "127.0.0.1",
            0,
            subprotocols=[Subprotocol("graphql-transport-ws")],
            process_request=process_request,
        ) as server:
            self.port = server.sockets[0].getsockname()[1]
            self._ready.set()
            await self._stop

    async def _handler(self, connection):
        try:
            while True:
                message = json.loads(await connection.recv())
                kind = message.get("type")
                if kind == "connection_init":
                    self.init_payload = message.get("payload")
                    if self.accept_auth:
                        await connection.send(json.dumps({"type": "connection_ack"}))
                    else:
                        await connection.close(4403, "Forbidden")
                        return
                elif kind == "subscribe":
                    self.subscribe_payload = message["payload"]
                    await self._play(connection, message["id"])
                elif kind == "pong":
                    self.pongs += 1
        except ConnectionClosed:
            pass

    async def _play(self, connection, sub_id):
        for action, *args in self.script:
            if action == "next":
                await connection.send(
                    json.dumps({"type": "next", "id": sub_id, "payload": args[0]})
                )
            elif action == "error":
                await connection.send(
                    json.dumps({"type": "error", "id": sub_id, "payload": args[0]})
                )
            elif action == "ping":
                await connection.send(json.dumps({"type": "ping"}))
            elif action == "complete":
                await connection.send(json.dumps({"type": "complete", "id": sub_id}))
            elif action == "close_abrupt":
                await connection.close(code=1011, reason="boom")
                return


@pytest.fixture
def ws_server():
    servers = []

    def factory(script=(), **kwargs):
        server = ScriptedWSServer(script, **kwargs).start()
        servers.append(server)
        return server

    yield factory
    for server in servers:
        server.stop()


def _sync_client(server, **kwargs):
    defaults = {"schema": "development", "token": "test-token", "timeout": 5.0}
    defaults.update(kwargs)
    return GPPClient(url=server.url, **defaults)


def _async_client(server, **kwargs):
    defaults = {"schema": "development", "token": "test-token", "timeout": 5.0}
    defaults.update(kwargs)
    return AsyncGPPClient(url=server.url, **defaults)


# ---------------------------------------------------------------------------
# Transport behavior, sync and async
# ---------------------------------------------------------------------------


def test_sync_watch_receives_events(ws_server):
    server = ws_server(
        [("next", PROGRAM_EVENT), ("next", PROGRAM_EVENT), ("complete",)]
    )
    with _sync_client(server) as client:
        events = list(client.programs.watch_edits(program_id="p-1"))
    assert len(events) == 2
    assert all(isinstance(e, ProgramEdit) for e in events)
    assert events[0].edit_type == "UPDATED"
    assert events[0].value.name == "Watched"
    assert server.init_payload == {"Authorization": "Bearer test-token"}
    assert server.subscribe_payload["operationName"] == "watchProgramEdits"
    assert server.subscribe_payload["variables"] == {"programId": "p-1"}
    assert "subscription watchProgramEdits" in server.subscribe_payload["query"]


async def test_async_watch_receives_events(ws_server):
    server = ws_server([("next", PROGRAM_EVENT), ("complete",)])
    async with _async_client(server) as client:
        events = [e async for e in client.programs.watch_edits(program_id="p-1")]
    assert len(events) == 1
    assert isinstance(events[0], ProgramEdit)
    assert events[0].value.id == "p-1"
    assert server.init_payload == {"Authorization": "Bearer test-token"}
    assert server.subscribe_payload["operationName"] == "watchProgramEdits"


def test_unset_variables_are_omitted(ws_server):
    server = ws_server([("complete",)])
    with _sync_client(server) as client:
        list(client.programs.watch_edits())
    assert server.subscribe_payload["variables"] == {}


def test_error_message_raises(ws_server):
    server = ws_server([("error", [{"message": "boom"}])])
    with _sync_client(server) as client, pytest.raises(GPPGraphQLError, match="boom"):
        list(client.programs.watch_edits())


def test_protocol_ping_is_answered(ws_server):
    server = ws_server([("ping",), ("next", PROGRAM_EVENT), ("complete",)])
    with _sync_client(server) as client:
        events = list(client.programs.watch_edits())
    assert len(events) == 1
    assert server.pongs == 1


def test_partial_event_warns_and_yields(ws_server, caplog):
    partial = {
        "data": {"programEdit": {"editType": "UPDATED", "value": {"id": "p-1"}}},
        "errors": [{"message": "background calculation pending"}],
    }
    server = ws_server([("next", partial), ("complete",)])
    with (
        caplog.at_level("WARNING", logger="gpp_client._executor"),
        _sync_client(server) as client,
    ):
        events = list(client.programs.watch_edits())
    assert len(events) == 1
    assert "partial data" in caplog.text


def test_event_with_all_roots_null_raises(ws_server):
    dead = {"data": {"programEdit": None}, "errors": [{"message": "gone"}]}
    server = ws_server([("next", dead)])
    with _sync_client(server) as client, pytest.raises(GPPGraphQLError, match="gone"):
        list(client.programs.watch_edits())


def test_abrupt_close_raises_connection_error(ws_server):
    server = ws_server([("next", PROGRAM_EVENT), ("close_abrupt",)])
    with _sync_client(server) as client:
        stream = client.programs.watch_edits()
        assert isinstance(next(stream), ProgramEdit)
        with pytest.raises(GPPConnectionError, match="closed before the server"):
            next(stream)


async def test_abrupt_close_raises_connection_error_async(ws_server):
    server = ws_server([("close_abrupt",)])
    async with _async_client(server) as client:
        with pytest.raises(GPPConnectionError, match="closed before the server"):
            async for _ in client.programs.watch_edits():
                pass


def test_auth_rejected_at_init_raises_auth_error(ws_server):
    server = ws_server(accept_auth=False)
    with _sync_client(server) as client, pytest.raises(GPPAuthError, match="4403"):
        list(client.programs.watch_edits())


def test_http_401_upgrade_raises_auth_error(ws_server):
    server = ws_server(http_status=401)
    with _sync_client(server) as client, pytest.raises(GPPAuthError, match="401"):
        list(client.programs.watch_edits())


def test_connection_refused_raises_connection_error():
    with (
        GPPClient(
            url="http://127.0.0.1:9", schema="development", token="t", timeout=2.0
        ) as client,
        pytest.raises(GPPConnectionError),
    ):
        list(client.programs.watch_edits())


def test_read_only_clients_can_subscribe(ws_server):
    server = ws_server([("complete",)])
    with _sync_client(server, read_only=True) as client:
        assert list(client.programs.watch_edits()) == []


def test_unavailable_operation_raises_eagerly(ws_server, monkeypatch):
    """The availability error surfaces at the call, before any connection."""
    server = ws_server()
    monkeypatch.setitem(
        OPERATION_TEXT,
        "watchProgramEdits",
        {"development": OPERATION_TEXT["watchProgramEdits"]["development"]},
    )
    with (
        _sync_client(server, schema="production") as client,
        pytest.raises(GPPOperationUnavailableError, match="watchProgramEdits"),
    ):
        client.programs.watch_edits()
    assert server.subscribe_payload is None


def test_other_watch_methods_share_the_transport(ws_server):
    """A second domain's watch method runs the same protocol end to end."""
    event = {
        "data": {
            "obscalcUpdate": {
                "editType": "UPDATED",
                "oldCalculationState": "CALCULATING",
                "newCalculationState": "READY",
                "value": {"id": "o-1"},
            }
        }
    }
    server = ws_server([("next", event), ("complete",)])
    with _sync_client(server) as client:
        events = list(client.scheduler.watch_observation_updates(executable_only=True))
    assert len(events) == 1
    assert isinstance(events[0], ObscalcUpdate)
    assert events[0].new_calculation_state == "READY"
    assert server.subscribe_payload["variables"] == {"executableOnly": True}


# ---------------------------------------------------------------------------
# Environment coverage: development, staging, and production
# ---------------------------------------------------------------------------


def test_every_subscription_has_operations():
    assert SUBSCRIPTION_OPERATIONS == [
        "watchObservationCalculations",
        "watchObservationEdits",
        "watchProgramEdits",
        "watchSchedulerObservationUpdates",
        "watchTargetEdits",
    ]


@pytest.mark.parametrize("spec", ENVIRONMENTS, ids=lambda s: s.name)
def test_subscriptions_available_in_every_environment(spec):
    """Each environment's schema source serves every subscription."""
    for operation in SUBSCRIPTION_OPERATIONS:
        assert spec.schema_source in OPERATION_TEXT[operation], (
            f"{operation} has no query text for {spec.name} "
            f"(schema source {spec.schema_source})"
        )


@pytest.mark.parametrize("spec", ENVIRONMENTS, ids=lambda s: s.name)
def test_ws_url_derives_from_every_deployed_environment(spec):
    if spec.base_url is None:
        pytest.skip(f"{spec.name} has no deployment yet")
    url = get_ws_url(spec.base_url)
    assert url.startswith("wss://")
    assert url.endswith("/ws")


def test_ws_url_scheme_mapping():
    assert get_ws_url("https://host.example") == "wss://host.example/ws"
    assert get_ws_url("http://127.0.0.1:8080") == "ws://127.0.0.1:8080/ws"


@pytest.mark.parametrize(
    "source", sorted({spec.schema_source for spec in ENVIRONMENTS})
)
def test_watch_works_with_each_schema_sources_text(ws_server, source):
    """The exact per-source query text goes over the wire and parses events."""
    server = ws_server([("next", PROGRAM_EVENT), ("complete",)])
    with _sync_client(server, schema=source) as client:
        events = list(client.programs.watch_edits())
    assert len(events) == 1
    assert (
        server.subscribe_payload["query"]
        == (OPERATION_TEXT["watchProgramEdits"][source])
    )
