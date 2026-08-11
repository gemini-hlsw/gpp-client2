"""
The ``gpp2`` command-line interface.

Every public method of every sync domain API becomes a command, derived by
reflection at startup: ``client.programs.get_by_id`` is ``gpp2 programs
get-by-id``. The CLI therefore cannot drift from the Python API - adding a
domain method adds its command, and a conformance test holds the two
surfaces together.

Parameter mapping:

- ``str``/``int``/``float``/``datetime``/``Enum`` parameters map to native
  options (enums render as choices).
- ``bool`` parameters map to ``--flag/--no-flag`` pairs that stay UNSET
  unless given, preserving server defaults.
- Pydantic input models map to a JSON option accepting an inline string or
  ``@path/to/file.json``.
- ``list`` parameters map to repeatable options.
- ``bytes`` parameters are skipped (the sibling file-path parameter covers
  them).
- Parameters not provided on the command line are omitted from the call,
  which preserves omit-vs-null semantics.

Subscriptions (``watch-*`` commands) stream one JSON document per event
until interrupted.
"""

from __future__ import annotations

import collections.abc
import enum
import inspect
import json
import typing
from datetime import datetime
from importlib import metadata
from inspect import Parameter, Signature
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, ValidationError

from gpp_client2._base import UnsetType
from gpp_client2.client import GPPClient
from gpp_client2.domains import DOMAIN_REGISTRY
from gpp_client2.errors import GPPError

__all__ = ["app", "main"]

app = typer.Typer(
    name="gpp2",
    help="Command-line interface for the Gemini Program Platform.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _make_client(settings: dict[str, Any]) -> GPPClient:
    """Build the client for one command invocation (tests monkeypatch this)."""
    return GPPClient(**settings)


def _version_callback(value: bool) -> None:
    if value:
        try:
            typer.echo(metadata.version("gpp-client2"))
        except metadata.PackageNotFoundError:  # pragma: no cover
            typer.echo("unknown")
        raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
    environment: str | None = typer.Option(
        None, "--environment", "-e", help="Target environment name."
    ),
    profile: str | None = typer.Option(
        None, help="Configuration profile from the config file."
    ),
    url: str | None = typer.Option(None, help="Explicit base URL, e.g. a local ODB."),
    schema: str | None = typer.Option(None, help="Schema source for a custom --url."),
    token: str | None = typer.Option(None, help="GPP API token."),
    read_only: bool = typer.Option(
        False, "--read-only", help="Refuse to execute mutations."
    ),
    timeout: float = typer.Option(30.0, help="Request timeout in seconds."),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the package version and exit.",
    ),
) -> None:
    """Configuration resolves like the Python client: explicit options, then
    GPP_* environment variables, then the config-file profile."""
    ctx.obj = {
        "environment": environment,
        "profile": profile,
        "url": url,
        "schema": schema,
        "token": token,
        "read_only": read_only,
        "timeout": timeout,
    }


# ---------------------------------------------------------------------------
# Rendering and JSON parameter parsing
# ---------------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return str(value)


def _render(result: Any) -> str:
    """Render a domain result: models and containers as JSON, text as-is."""
    if isinstance(result, BaseModel):
        return result.model_dump_json(indent=2, by_alias=True, exclude_unset=True)
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=_json_default)


def _parse_json_argument(raw: str, model: type[BaseModel] | None, name: str) -> Any:
    """Parse a JSON option value, honoring the ``@file`` convention."""
    text = raw
    if raw.startswith("@"):
        path = Path(raw[1:]).expanduser()
        if not path.is_file():
            raise typer.BadParameter(f"File not found: {path}", param_hint=name)
        text = path.read_text(encoding="utf-8")
    try:
        if model is not None:
            return model.model_validate_json(text)
        return json.loads(text)
    except (ValidationError, ValueError) as exc:
        raise typer.BadParameter(f"Invalid JSON for --{name}: {exc}") from exc


# ---------------------------------------------------------------------------
# Parameter classification
# ---------------------------------------------------------------------------


class _ParamKind(enum.Enum):
    NATIVE = "native"
    FLAG = "flag"
    JSON_MODEL = "json_model"
    JSON_VALUE = "json_value"
    LIST = "list"
    SKIP = "skip"


def _unwrap_annotation(annotation: Any) -> list[Any]:
    """Flatten Optional/Union/Annotated annotations to their members."""
    origin = typing.get_origin(annotation)
    if origin is Annotated:
        return _unwrap_annotation(typing.get_args(annotation)[0])
    if origin in (typing.Union, __import__("types").UnionType):
        members: list[Any] = []
        for argument in typing.get_args(annotation):
            members.extend(_unwrap_annotation(argument))
        return members
    return [annotation]


def _classify(annotation: Any) -> tuple[_ParamKind, Any]:
    """Map a domain-method parameter annotation to a CLI representation."""
    members = [
        m
        for m in _unwrap_annotation(annotation)
        if m not in (type(None), UnsetType, Any, Parameter.empty)
    ]

    for member in members:
        if isinstance(member, type) and issubclass(member, BaseModel):
            return _ParamKind.JSON_MODEL, member
    for member in members:
        if typing.get_origin(member) in (list, tuple) or member in (list, tuple):
            return _ParamKind.LIST, None
    if any(member is bytes for member in members):
        return _ParamKind.SKIP, None
    if any(member is bool for member in members):
        return _ParamKind.FLAG, None
    for candidate in (int, float, datetime):
        if candidate in members:
            return _ParamKind.NATIVE, candidate
    for member in members:
        if isinstance(member, type) and issubclass(member, enum.Enum):
            return _ParamKind.NATIVE, member
    if any(typing.get_origin(m) is dict or m is dict for m in members):
        return _ParamKind.JSON_VALUE, None
    return _ParamKind.NATIVE, str


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


def _summary(method: Any, method_name: str, attribute: str) -> str:
    """First docstring line, or a derived fallback."""
    doc = inspect.getdoc(method) or ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('"""'):
            return stripped
    verb = method_name.split("_")[0].capitalize()
    return f"{verb} {attribute.replace('_', ' ')}."


def _resolve_hints(method: Any) -> dict[str, Any]:
    try:
        return typing.get_type_hints(method)
    except Exception:  # pragma: no cover - defensive for exotic annotations
        return {}


def _is_stream(method: Any) -> bool:
    """Whether a sync domain method returns a subscription iterator."""
    return_hint = _resolve_hints(method).get("return")
    return typing.get_origin(return_hint) is collections.abc.Iterator


def _build_command(attribute: str, method_name: str, method: Any) -> Any:
    """Build one Typer command wrapping a sync domain method."""
    hints = _resolve_hints(method)
    cli_parameters: list[Parameter] = [
        Parameter("ctx", Parameter.POSITIONAL_OR_KEYWORD, annotation=typer.Context)
    ]
    # name -> (kind, model)
    plan: dict[str, tuple[_ParamKind, Any]] = {}

    for parameter in inspect.signature(method).parameters.values():
        if parameter.name == "self" or parameter.kind in (
            Parameter.VAR_KEYWORD,
            Parameter.VAR_POSITIONAL,
        ):
            continue
        annotation = hints.get(parameter.name, parameter.annotation)
        kind, mapped = _classify(annotation)
        if kind is _ParamKind.SKIP:
            continue

        required = parameter.default is Parameter.empty
        option_name = f"--{parameter.name.replace('_', '-')}"

        cli_annotation: Any
        help_text = "See the API reference for details."
        if kind is _ParamKind.JSON_MODEL:
            cli_annotation = str | None
            help_text = f"{mapped.__name__} as inline JSON or @path/to/file.json."
        elif kind is _ParamKind.JSON_VALUE:
            cli_annotation = str | None
            help_text = "Inline JSON or @path/to/file.json."
        elif kind is _ParamKind.LIST:
            cli_annotation = list[str] | None
            help_text = "Repeatable."
        elif kind is _ParamKind.FLAG:
            cli_annotation = bool | None
        else:
            cli_annotation = mapped if required else (mapped | None)

        default = (
            typer.Option(..., option_name, help=help_text)
            if required
            else typer.Option(None, help=help_text)
        )
        cli_parameters.append(
            Parameter(
                parameter.name,
                Parameter.KEYWORD_ONLY,
                default=default,
                annotation=cli_annotation,
            )
        )
        plan[parameter.name] = (kind, mapped)

    stream = _is_stream(method)

    def command(**cli_kwargs: Any) -> None:
        ctx: typer.Context = cli_kwargs.pop("ctx")
        call_kwargs: dict[str, Any] = {}
        for name, value in cli_kwargs.items():
            if value is None:
                continue  # not given: omit, keeping UNSET/default semantics
            kind, mapped = plan[name]
            if kind in (_ParamKind.JSON_MODEL, _ParamKind.JSON_VALUE):
                value = _parse_json_argument(value, mapped, name)
            elif kind is _ParamKind.LIST:
                value = list(value)
            call_kwargs[name] = value

        try:
            with _make_client(ctx.obj) as client:
                bound = getattr(getattr(client, attribute), method_name)
                if stream:
                    typer.echo("Streaming events; press Ctrl-C to stop.", err=True)
                    for event in bound(**call_kwargs):
                        typer.echo(_render(event))
                    return
                result = bound(**call_kwargs)
        except GPPError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(_render(result))

    command.__signature__ = Signature(cli_parameters)  # type: ignore[attr-defined]
    command.__annotations__ = {
        p.name: p.annotation for p in cli_parameters if p.annotation is not p.empty
    }
    command.__doc__ = _summary(method, method_name, attribute)
    command.__name__ = method_name
    return command


def _attach_domain_commands(root: typer.Typer) -> None:
    """Create one command group per domain, one command per public method."""
    for attribute, sync_cls, _ in DOMAIN_REGISTRY.values():
        group = typer.Typer(
            name=attribute.replace("_", "-"),
            help=f"{attribute.replace('_', ' ').capitalize()} operations.",
            no_args_is_help=True,
        )
        for method_name, method in sorted(
            inspect.getmembers(sync_cls, predicate=callable)
        ):
            if method_name.startswith("_"):
                continue
            group.command(method_name.replace("_", "-"))(
                _build_command(attribute, method_name, method)
            )
        root.add_typer(group)


# ---------------------------------------------------------------------------
# Root commands
# ---------------------------------------------------------------------------


@app.command()
def ping(ctx: typer.Context) -> None:
    """Check that the deployment is reachable and the token works."""
    with _make_client(ctx.obj) as client:
        ok, reason = client.ping()
    if ok:
        typer.echo(f"ok: {client.environment} is reachable")
    else:
        typer.echo(f"error: {reason}", err=True)
        raise typer.Exit(code=1)


@app.command()
def graphql(
    ctx: typer.Context,
    query: str = typer.Argument(help="GraphQL text, or @path/to/file.graphql."),
    variables: str | None = typer.Option(
        None, help="Variables as inline JSON or @path/to/file.json."
    ),
    operation_name: str | None = typer.Option(
        None, help="Operation to run when the document has several."
    ),
) -> None:
    """Execute a raw GraphQL operation (the escape hatch)."""
    if query.startswith("@"):
        path = Path(query[1:]).expanduser()
        if not path.is_file():
            raise typer.BadParameter(f"File not found: {path}", param_hint="query")
        query = path.read_text(encoding="utf-8")
    parsed = (
        _parse_json_argument(variables, None, "variables")
        if variables is not None
        else None
    )
    try:
        with _make_client(ctx.obj) as client:
            data = client.graphql(query, parsed, operation_name=operation_name)
    except GPPError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(data, indent=2, default=_json_default))


_attach_domain_commands(app)

click_app = typer.main.get_command(app)
"""The CLI as a click object; sphinx-click documents the tree through it."""


def main() -> None:
    """Console-script entry point."""
    app()
