"""
CLI conformance and behavior.

The CLI derives from the sync domain APIs by reflection; the conformance
test here pins the rule that every public method is a command. Behavior
tests run commands end to end through Typer with a mock HTTP transport, and
the subscription command streams from the scripted WebSocket server.
"""

import inspect
import json

import httpx
import pytest
from typer.testing import CliRunner

import gpp_client2.cli as cli
from gpp_client2 import GPPClient
from gpp_client2.domains import DOMAIN_REGISTRY
from tests.conftest import RecordingHandler, graphql_response
from tests.test_subscriptions import PROGRAM_EVENT, ScriptedWSServer

runner = CliRunner()


def _group_commands() -> dict[str, set[str]]:
    """Registered command names per domain group."""
    groups = {}
    for group_info in cli.app.registered_groups:
        instance = group_info.typer_instance
        groups[instance.info.name] = {
            command.name for command in instance.registered_commands
        }
    return groups


def test_every_domain_method_is_a_command():
    """The reflective rule: one group per domain, one command per method."""
    groups = _group_commands()
    for attribute, sync_cls, _ in DOMAIN_REGISTRY.values():
        group_name = attribute.replace("_", "-")
        assert group_name in groups, f"missing command group {group_name}"
        for name, _member in inspect.getmembers(sync_cls, predicate=callable):
            if name.startswith("_"):
                continue
            command = name.replace("_", "-")
            assert command in groups[group_name], (
                f"gpp {group_name} {command} is missing"
            )


@pytest.fixture
def cli_client(monkeypatch):
    """Route CLI-created clients through a recording mock transport."""
    state: dict[str, RecordingHandler] = {}

    def factory(*responses: httpx.Response):
        handler = RecordingHandler(*responses)

        def make_client(settings):
            return GPPClient(
                url="http://odb.test",
                schema="development",
                token="cli-token",
                read_only=settings.get("read_only", False),
                transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(cli, "_make_client", make_client)
        state["handler"] = handler
        return handler

    return factory


def test_get_by_id_renders_model_json(cli_client):
    handler = cli_client(graphql_response({"program": {"id": "p-1", "name": "N"}}))
    result = runner.invoke(cli.app, ["programs", "get-by-id", "--program-id", "p-1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"id": "p-1", "name": "N"}
    assert handler.last_body["operationName"] == "getProgramById"
    assert handler.last_body["variables"] == {"programId": "p-1"}


def test_json_model_option_inline(cli_client):
    handler = cli_client(graphql_response({"createProgram": {"program": {"id": "p"}}}))
    result = runner.invoke(
        cli.app,
        ["programs", "create", "--properties", '{"name": "From CLI"}'],
    )
    assert result.exit_code == 0, result.output
    sent = handler.last_body["variables"]["properties"]
    assert sent == {"name": "From CLI"}


def test_json_model_option_from_file(cli_client, tmp_path):
    handler = cli_client(graphql_response({"createProgram": {"program": {"id": "p"}}}))
    payload = tmp_path / "props.json"
    payload.write_text('{"name": "From file"}', encoding="utf-8")
    result = runner.invoke(
        cli.app, ["programs", "create", "--properties", f"@{payload}"]
    )
    assert result.exit_code == 0, result.output
    assert handler.last_body["variables"]["properties"] == {"name": "From file"}


def test_invalid_json_is_a_parameter_error(cli_client):
    cli_client()
    result = runner.invoke(cli.app, ["programs", "create", "--properties", "{nope"])
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output


def test_omitted_flag_stays_unset(cli_client):
    handler = cli_client(
        graphql_response({"programs": {"hasMore": False, "matches": []}})
    )
    result = runner.invoke(cli.app, ["programs", "get-all"])
    assert result.exit_code == 0, result.output
    assert "includeDeleted" not in handler.last_body["variables"]


def test_given_flag_is_sent(cli_client):
    handler = cli_client(
        graphql_response({"programs": {"hasMore": False, "matches": []}})
    )
    result = runner.invoke(cli.app, ["programs", "get-all", "--include-deleted"])
    assert result.exit_code == 0, result.output
    assert handler.last_body["variables"]["includeDeleted"] is True


def test_gpp_error_exits_nonzero(cli_client):
    cli_client(httpx.Response(401, json={}))
    result = runner.invoke(cli.app, ["programs", "get-by-id", "--program-id", "p-1"])
    assert result.exit_code == 1
    assert "error:" in result.output


def test_ping_command(cli_client):
    cli_client(graphql_response({"programs": {"matches": []}}))
    result = runner.invoke(cli.app, ["ping"])
    assert result.exit_code == 0
    assert "ok:" in result.output


def test_graphql_command(cli_client):
    handler = cli_client(graphql_response({"x": 1}))
    result = runner.invoke(
        cli.app, ["graphql", "query Q($a: Int) { x }", "--variables", '{"a": 2}']
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"x": 1}
    assert handler.last_body["variables"] == {"a": 2}


def test_version_option():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_watch_command_streams_events():
    """The subscription command streams JSON documents over a real socket."""
    server = ScriptedWSServer(
        [("next", PROGRAM_EVENT), ("next", PROGRAM_EVENT), ("complete",)]
    ).start()
    try:
        result = runner.invoke(
            cli.app,
            [
                "--url",
                server.url,
                "--schema",
                "development",
                "--token",
                "cli-token",
                "programs",
                "watch-edits",
                "--program-id",
                "p-1",
            ],
        )
        assert result.exit_code == 0, result.output
        assert result.stdout.count('"editType": "UPDATED"') == 2
        assert server.subscribe_payload["variables"] == {"programId": "p-1"}
    finally:
        server.stop()
