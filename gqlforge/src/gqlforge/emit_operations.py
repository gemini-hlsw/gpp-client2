"""
Emit the operation map and the generated domain layer.

For every operation this derives a Python method: its name from the naming
convention, its signature from the operation's variable definitions, and its
return type by unwrapping single-field selection chains at the root, so
``createProgram { program { ... } }`` returns a ``Program`` rather than a
wrapper. Sync and async variants are generated from the same spec.
"""

from dataclasses import dataclass

from gqlforge import GqlforgeError
from gqlforge.config import Config
from gqlforge.emit_models import GENERATED_HEADER, render_type
from gqlforge.naming import (
    method_name_for_operation,
    python_field_name,
    to_pascal,
    to_snake,
)
from gqlforge.prune import PruneResult, collect_transitive_spreads
from gqlforge.schema import field_availability
from graphql import (
    DocumentNode,
    FieldNode,
    GraphQLNonNull,
    GraphQLSchema,
    OperationDefinitionNode,
    get_named_type,
    print_ast,
)


@dataclass
class Variable:
    """One operation variable, as both GraphQL and Python see it."""

    graphql_name: str
    python_name: str
    annotation: str
    graphql_type: str
    required: bool
    default_text: str | None


@dataclass
class OperationSpec:
    """Everything needed to generate one domain method."""

    name: str
    kind: str
    domain: str
    method_name: str
    variables: list[Variable]
    unwrap_path: tuple[str, ...]
    return_annotation: str
    summary: str | None
    doc: str | None = None


def _real_fields(selection_set) -> list[FieldNode]:
    """Field selections excluding ``__typename``; empty when mixed content."""
    fields = []
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            if selection.name.value != "__typename":
                fields.append(selection)
        else:
            return []  # fragment spread or inline fragment: stop unwrapping
    return fields


def build_operation_specs(
    document: DocumentNode,
    schema: GraphQLSchema,
    domains: dict[str, str],
    docs: dict[str, str] | None = None,
) -> list[OperationSpec]:
    """Derive an OperationSpec for every operation in the union document."""
    root_types = {
        "query": schema.query_type,
        "mutation": schema.mutation_type,
        "subscription": schema.subscription_type,
    }
    specs = []
    method_names: dict[tuple[str, str], str] = {}

    for definition in document.definitions:
        if not isinstance(definition, OperationDefinitionNode):
            continue
        name = definition.name.value
        kind = definition.operation.value
        domain = domains[name]
        try:
            method_name = method_name_for_operation(name, domain)
        except ValueError as exc:
            raise GqlforgeError(str(exc)) from exc

        collision = method_names.get((domain, method_name))
        if collision is not None:
            raise GqlforgeError(
                f"Operations '{collision}' and '{name}' both derive method "
                f"'{method_name}' in domain '{domain}'."
            )
        method_names[(domain, method_name)] = name

        variables = []
        for var_def in definition.variable_definitions:
            graphql_name = var_def.variable.name.value
            gql_type = _type_from_node(var_def.type, schema)
            required = var_def.default_value is None and isinstance(
                gql_type, GraphQLNonNull
            )
            annotation = render_type(gql_type)
            if not required:
                annotation += " | UnsetType"
            variables.append(
                Variable(
                    graphql_name=graphql_name,
                    python_name=python_field_name(graphql_name),
                    annotation=annotation,
                    graphql_type=print_ast(var_def.type),
                    required=required,
                    default_text=(
                        print_ast(var_def.default_value)
                        if var_def.default_value is not None
                        else None
                    ),
                )
            )
        variables.sort(key=lambda v: not v.required)

        unwrap_path, return_annotation, summary = _derive_return(
            definition, root_types[kind], name
        )
        specs.append(
            OperationSpec(
                name=name,
                kind=kind,
                domain=domain,
                method_name=method_name,
                variables=variables,
                unwrap_path=unwrap_path,
                return_annotation=return_annotation,
                summary=summary,
                doc=(docs or {}).get(name),
            )
        )
    return specs


def _type_from_node(type_node, schema):
    """Resolve a variable's AST type node into a GraphQL type instance."""
    from graphql.language import ast as gql_ast

    from graphql import GraphQLList

    if isinstance(type_node, gql_ast.NonNullTypeNode):
        return GraphQLNonNull(_type_from_node(type_node.type, schema))
    if isinstance(type_node, gql_ast.ListTypeNode):
        return GraphQLList(_type_from_node(type_node.type, schema))
    named = schema.type_map.get(type_node.name.value)
    if named is None:
        raise GqlforgeError(
            f"Variable type '{type_node.name.value}' is not in the merged schema."
        )
    return named


def _derive_return(
    definition: OperationDefinitionNode, root_type, operation_name: str
) -> tuple[tuple[str, ...], str, str | None]:
    """Unwrap single-field selection chains at the root of an operation."""
    fields = _real_fields(definition.selection_set)
    if len(fields) != 1:
        raise GqlforgeError(
            f"Operation '{operation_name}' selects {len(fields)} root fields; "
            "exactly one is supported. Split the operation or extend codegen."
        )

    path: list[str] = []
    nullable = False
    parent_type = root_type
    field_node = fields[0]
    while True:
        field_name = field_node.name.value
        response_key = field_node.alias.value if field_node.alias else field_name
        field_def = parent_type.fields.get(field_name)
        if field_def is None:
            raise GqlforgeError(
                f"Operation '{operation_name}' selects unknown field "
                f"'{parent_type.name}.{field_name}'."
            )
        path.append(response_key)
        if not isinstance(field_def.type, GraphQLNonNull):
            nullable = True
        if len(path) == 1:
            summary = field_def.description
        if field_node.selection_set is None:
            break
        inner = _real_fields(field_node.selection_set)
        # Stop when the wire type stops being a plain object chain (a list
        # boundary keeps its container model) or the shape widens.
        if len(inner) != 1 or "list[" in render_type(field_def.type):
            break
        parent_type = get_named_type(field_def.type)
        field_node = inner[0]

    annotation = render_type(field_def.type, nullable_suffix=False)
    if nullable and not annotation.endswith("| None"):
        annotation += " | None"
    return tuple(path), annotation, summary


# ---------------------------------------------------------------------------
# Operation map emission
# ---------------------------------------------------------------------------


def _restricted_field_names(
    availability: dict[str, tuple[str, ...]],
    schemas: dict[str, GraphQLSchema],
    sources: list[str],
) -> dict[str, tuple[str, ...]]:
    """
    Map unambiguous field NAMES to their availability.

    Used to pre-flight raw (runtime-built) operations, which cannot be
    type-resolved without shipping the schema. A name qualifies only when
    every type carrying it has identical availability; ambiguous names are
    omitted rather than guessed.
    """
    from collections import defaultdict

    name_availabilities: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    all_sources = tuple(sources)

    for source in sources:
        for type_name, graphql_type in schemas[source].type_map.items():
            if type_name.startswith("__"):
                continue
            for field_name in getattr(graphql_type, "fields", None) or {}:
                pair = f"{type_name}.{field_name}"
                name_availabilities[field_name].add(
                    tuple(availability.get(pair, all_sources))
                )

    restricted = {}
    for name, availabilities in name_availabilities.items():
        if len(availabilities) == 1:
            entry = next(iter(availabilities))
            if entry != all_sources:
                restricted[name] = entry
    return dict(sorted(restricted.items()))


def emit_operation_map(
    specs: list[OperationSpec],
    prune_results: dict[str, PruneResult],
    schemas: dict[str, GraphQLSchema],
    sources: list[str],
) -> str:
    """Render the _generated/operations.py module."""
    texts: dict[str, dict[str, str]] = {}
    for source in sources:
        result = prune_results[source]
        texts[source] = {}
        for name, operation in result.operations.items():
            spreads = collect_transitive_spreads(
                operation.selection_set, result.fragments
            )
            definitions = [operation] + [
                result.fragments[s] for s in sorted(spreads) if s in result.fragments
            ]
            texts[source][name] = print_ast(
                DocumentNode(definitions=tuple(definitions))
            )

    text_to_var: dict[str, str] = {}
    constants: list[str] = []
    for spec in sorted(specs, key=lambda s: s.name):
        for source in sources:
            text = texts[source].get(spec.name)
            if text is None or text in text_to_var:
                continue
            var = f"_T{len(text_to_var)}"
            text_to_var[text] = var
            constants.append(f'{var} = """\\\n{text}"""')

    entries = []
    kind_entries = []
    domain_entries = []
    for spec in sorted(specs, key=lambda s: s.name):
        per_source = {
            source: text_to_var[texts[source][spec.name]]
            for source in sources
            if spec.name in texts[source]
        }
        rendered = ", ".join(f'"{s}": {v}' for s, v in per_source.items())
        entries.append(f'    "{spec.name}": {{{rendered}}},')
        kind_entries.append(f'    "{spec.name}": "{spec.kind}",')
        domain_entries.append(f'    "{spec.name}": "{spec.domain}",')

    availability = field_availability(schemas, sources)
    availability_entries = [
        f'    "{pair}": {tuple(avail)!r},' for pair, avail in availability.items()
    ]
    restricted = _restricted_field_names(availability, schemas, sources)
    restricted_entries = [
        f'    "{name}": {tuple(avail)!r},' for name, avail in restricted.items()
    ]

    lines = [
        GENERATED_HEADER,
        f"SCHEMA_SOURCES: tuple[str, ...] = {tuple(sources)!r}",
        '"""Committed schema sources, newest first."""',
        "",
        *constants,
        "",
        "OPERATION_TEXT: dict[str, dict[str, str]] = {",
        *entries,
        "}",
        '"""Executable text per operation per schema source. An operation absent',
        'from a source\'s entry is unavailable in that environment."""',
        "",
        "OPERATION_KIND: dict[str, str] = {",
        *kind_entries,
        "}",
        "",
        "OPERATION_DOMAIN: dict[str, str] = {",
        *domain_entries,
        "}",
        "",
        "FIELD_AVAILABILITY: dict[str, tuple[str, ...]] = {",
        *availability_entries,
        "}",
        '"""Type.field pairs not present in every schema source."""',
        "",
        "RESTRICTED_FIELD_NAMES: dict[str, tuple[str, ...]] = {",
        *restricted_entries,
        "}",
        '"""Field names with restricted, unambiguous availability, used to',
        'pre-flight raw operations."""',
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Domain base emission
# ---------------------------------------------------------------------------


def _method_docstring(spec: OperationSpec, indent: str) -> list[str]:
    """
    Numpydoc docstring for a generated method.

    The opening comes from the operation's leading ``#`` comment block
    verbatim when the author wrote one, else from the schema's root-field
    description, else a generic sentence. Parameter and return sections
    are always derived.
    """
    lines = [f'{indent}"""']
    if spec.doc:
        for line in spec.doc.splitlines():
            lines.append(f"{indent}{line}".rstrip())
    else:
        raw = spec.summary or f"Run the ``{spec.name}`` {spec.kind}."
        sentence = " ".join(raw.split()).split(". ")[0].rstrip(".") + "."
        lines.append(f"{indent}{sentence}")
    if spec.variables:
        lines.append("")
        lines.append(f"{indent}Parameters")
        lines.append(f"{indent}----------")
        for variable in spec.variables:
            lines.append(f"{indent}{variable.python_name} : {variable.annotation}")
            detail = f"GraphQL variable ``${variable.graphql_name}`` "
            detail += f"(``{variable.graphql_type}``"
            if variable.default_text is not None:
                detail += f", server default ``{variable.default_text}``"
            detail += ")."
            lines.append(f"{indent}    {detail}")
    lines.append("")
    if spec.kind == "subscription":
        lines.append(f"{indent}Yields")
        lines.append(f"{indent}------")
        lines.append(f"{indent}{spec.return_annotation}")
        lines.append(
            f"{indent}    Parsed from ``data.{'.'.join(spec.unwrap_path)}`` in "
            "each event. Iteration ends when the server completes the"
        )
        lines.append(f"{indent}    subscription.")
    else:
        lines.append(f"{indent}Returns")
        lines.append(f"{indent}-------")
        lines.append(f"{indent}{spec.return_annotation}")
        lines.append(
            f"{indent}    Parsed from ``data.{'.'.join(spec.unwrap_path)}`` in "
            "the response."
        )
    lines.append(f'{indent}"""')
    return lines


def _method_source(spec: OperationSpec, *, is_async: bool) -> list[str]:
    """Source lines for one generated method."""
    adapter = f"_a_{to_snake(spec.name)}"
    params = ["self"]
    required = [v for v in spec.variables if v.required]
    optional = [v for v in spec.variables if not v.required]
    for variable in required:
        params.append(f"{variable.python_name}: {variable.annotation}")
    if optional:
        params.append("*")
        for variable in optional:
            params.append(f"{variable.python_name}: {variable.annotation} = UNSET")

    if spec.kind == "subscription":
        return _subscription_method_source(spec, params, adapter, is_async=is_async)

    prefix = "async def" if is_async else "def"
    awaiting = "await " if is_async else ""
    lines = [f"    {prefix} {spec.method_name}("]
    lines.extend(f"        {p}," for p in params)
    lines.append(f"    ) -> {spec.return_annotation}:")
    lines.extend(_method_docstring(spec, "        "))
    lines.append("        data = " + awaiting + "self._executor.run(")
    lines.append(f'            "{spec.name}",')
    lines.append("            {")
    for variable in spec.variables:
        lines.append(
            f'                "{variable.graphql_name}": {variable.python_name},'
        )
    lines.append("            },")
    lines.append("        )")
    lines.append(
        f"        return {adapter}.validate_python(_unwrap(data, {spec.unwrap_path!r}))"
    )
    lines.append("")
    return lines


def _subscription_method_source(
    spec: OperationSpec, params: list[str], adapter: str, *, is_async: bool
) -> list[str]:
    """
    Source lines for one generated subscription method.

    A plain ``def`` in both variants: it pre-flights availability and builds
    the payload eagerly, then returns the (sync or async) event iterator, so
    environment errors surface at the call site rather than mid-iteration.
    """
    iterator = "AsyncIterator" if is_async else "Iterator"
    mapper = "_map_astream" if is_async else "_map_stream"
    lines = [f"    def {spec.method_name}("]
    lines.extend(f"        {p}," for p in params)
    lines.append(f"    ) -> {iterator}[{spec.return_annotation}]:")
    lines.extend(_method_docstring(spec, "        "))
    lines.append("        stream = self._executor.stream(")
    lines.append(f'            "{spec.name}",')
    lines.append("            {")
    for variable in spec.variables:
        lines.append(
            f'                "{variable.graphql_name}": {variable.python_name},'
        )
    lines.append("            },")
    lines.append("        )")
    lines.append(f"        return {mapper}(stream, {adapter}, {spec.unwrap_path!r})")
    lines.append("")
    return lines


def emit_domains(specs: list[OperationSpec], config: Config) -> str:
    """Render the _generated/domains.py module with sync and async bases."""
    domains: dict[str, list[OperationSpec]] = {}
    for spec in specs:
        domains.setdefault(spec.domain, []).append(spec)

    lines = [
        GENERATED_HEADER,
        "from __future__ import annotations",
        "",
        "from collections.abc import AsyncIterator, Iterator  # noqa: F401",
        "",
        "from pydantic import TypeAdapter",
        "",
        f"from {config.runtime_package}._base import UNSET, UnsetType  # noqa: F401",
        f"from {config.runtime_package}._executor import AsyncExecutor, SyncExecutor",
        f"from {config.generated_package}.enums import *  # noqa: F401,F403",
        f"from {config.generated_package}.inputs import *  # noqa: F401,F403",
        f"from {config.generated_package}.models import *  # noqa: F401,F403",
        f"from {config.generated_package}.scalars import *  # noqa: F401,F403",
        "",
        "",
        "def _unwrap(data, path):",
        '    """Follow a response-key path, short-circuiting on null."""',
        "    current = data",
        "    for key in path:",
        "        if current is None:",
        "            return None",
        "        current = current.get(key)",
        "    return current",
        "",
        "",
        "def _map_stream(stream, adapter, path):",
        '    """Parse each subscription event with the operation\'s adapter."""',
        "    for data in stream:",
        "        yield adapter.validate_python(_unwrap(data, path))",
        "",
        "",
        "async def _map_astream(stream, adapter, path):",
        '    """Async twin of :func:`_map_stream`."""',
        "    async for data in stream:",
        "        yield adapter.validate_python(_unwrap(data, path))",
        "",
    ]

    for spec in sorted(specs, key=lambda s: s.name):
        adapter = f"_a_{to_snake(spec.name)}"
        lines.append(f"{adapter} = TypeAdapter({spec.return_annotation})")
    lines.append("")

    class_names = []
    for domain in sorted(domains):
        domain_specs = sorted(domains[domain], key=lambda s: s.method_name)
        for is_async in (False, True):
            prefix = "Async" if is_async else ""
            class_name = f"{prefix}{to_pascal(domain)}Operations"
            class_names.append(class_name)
            executor_type = "AsyncExecutor" if is_async else "SyncExecutor"
            lines.append("")
            lines.append(f"class {class_name}:")
            lines.append(
                f'    """Generated {spec_kind_word(is_async)} operations for the '
                f'``{domain}`` domain."""'
            )
            lines.append("")
            lines.append(f'    _DOMAIN = "{domain}"')
            lines.append("")
            lines.append(f"    def __init__(self, executor: {executor_type}) -> None:")
            lines.append("        self._executor = executor")
            lines.append("")
            for spec in domain_specs:
                lines.extend(_method_source(spec, is_async=is_async))

    lines.append("")
    lines.append(f"__all__ = {sorted(class_names)!r}")
    lines.append("")
    return "\n".join(lines)


def spec_kind_word(is_async: bool) -> str:
    """Human word for the sync/async variant in docstrings."""
    return "async" if is_async else "sync"


def emit_client(specs: list[OperationSpec], config: Config) -> str:
    """Emit client.py: default sync and async clients over every domain."""
    domains = sorted({spec.domain for spec in specs})
    pairs = []  # (attribute, sync class, async class)
    for domain in domains:
        pascal = to_pascal(domain)
        pairs.append(
            (domain or "ops", f"{pascal}Operations", f"Async{pascal}Operations")
        )

    domain_imports = sorted(name for _, s, a in pairs for name in (s, a))
    lines = [
        GENERATED_HEADER,
        "from __future__ import annotations",
        "",
        "from typing import Any, Self",
        "",
        "import httpx",
        "",
        "from ._executor import AsyncExecutor, ExecutorCore, SyncExecutor",
        "from ._ws import AsyncWsTransport, SyncWsTransport, WsConfig, get_ws_url",
        "from .domains import (",
        *[f"    {name}," for name in domain_imports],
        ")",
        "from .operations import SCHEMA_SOURCES",
        "",
        '__all__ = ["AsyncClient", "Client"]',
        "",
    ]

    for is_async in (False, True):
        class_name = "AsyncClient" if is_async else "Client"
        http_class = "httpx.AsyncClient" if is_async else "httpx.Client"
        executor_class = "AsyncExecutor" if is_async else "SyncExecutor"
        ws_class = "AsyncWsTransport" if is_async else "SyncWsTransport"
        a = "async " if is_async else ""
        await_ = "await " if is_async else ""
        lines += [
            "",
            f"class {class_name}:",
            '    """',
            f"    {'Asynchronous' if is_async else 'Synchronous'} client: "
            "one attribute per domain.",
            "",
            "    Parameters",
            "    ----------",
            "    url : str",
            "        The GraphQL endpoint.",
            "    token : str | None",
            "        Bearer token, sent on HTTP and WebSocket requests.",
            "    source : str | None",
            "        Schema source whose query text to send; defaults to the",
            "        newest (``SCHEMA_SOURCES[0]``).",
            "    read_only : bool",
            "        Refuse to execute mutations before any network call.",
            "    timeout : float",
            "        Request and WebSocket-handshake timeout in seconds.",
            "    headers : dict[str, str] | None",
            "        Extra HTTP headers.",
            "    transport : httpx.BaseTransport | None",
            "        Transport injection, e.g. ``httpx.MockTransport`` in tests.",
            "    ws_url : str | None",
            "        Subscription endpoint; defaults to ``url`` with the scheme",
            "        swapped to ``ws(s)``.",
            '    """',
            "",
            "    executor_core_class: type[ExecutorCore] = ExecutorCore",
            '    """Override to specialize payloads, processing, or error types."""',
            "",
            "    def __init__(",
            "        self,",
            "        url: str,",
            "        *,",
            "        token: str | None = None,",
            "        source: str | None = None,",
            "        read_only: bool = False,",
            "        timeout: float = 30.0,",
            "        headers: dict[str, str] | None = None,",
            "        transport: Any = None,",
            "        ws_url: str | None = None,",
            "    ) -> None:",
            "        self.source = source or SCHEMA_SOURCES[0]",
            "        request_headers = dict(headers or {})",
            "        if token:",
            '            request_headers["Authorization"] = f"Bearer {token}"',
            f"        self._http = {http_class}(",
            "            base_url=url,",
            "            headers=request_headers,",
            "            timeout=timeout,",
            "            transport=transport,",
            "        )",
            "        core = self.executor_core_class(",
            "            source=self.source, read_only=read_only",
            "        )",
            f"        ws = {ws_class}(",
            "            WsConfig(",
            "                url=ws_url or get_ws_url(url),",
            '                token=token or "",',
            "                connect_timeout=timeout,",
            "            ),",
            "            core,",
            "        )",
            f"        self._executor = {executor_class}(self._http, core, ws, url=url)",
            "        self._wire_domains()",
            "",
            "    def _wire_domains(self) -> None:",
            '        """Attach one API object per domain; override to specialize."""',
        ]
        for attribute, sync_cls, async_cls in pairs:
            domain_class = async_cls if is_async else sync_cls
            lines.append(f"        self.{attribute} = {domain_class}(self._executor)")
        lines += [
            "",
            f"    {a}def graphql(",
            "        self,",
            "        query: str,",
            "        variables: dict[str, Any] | None = None,",
            "        operation_name: str | None = None,",
            "    ) -> Any:",
            '        """Execute a raw operation and return the ``data`` dict."""',
            f"        return {await_}self._executor.run_raw("
            "query, variables, operation_name)",
            "",
        ]
        if is_async:
            lines += [
                "    async def aclose(self) -> None:",
                "        await self._http.aclose()",
                "",
                "    async def __aenter__(self) -> Self:",
                "        return self",
                "",
                "    async def __aexit__(self, *exc_info: object) -> None:",
                "        await self.aclose()",
            ]
        else:
            lines += [
                "    def close(self) -> None:",
                "        self._http.close()",
                "",
                "    def __enter__(self) -> Self:",
                "        return self",
                "",
                "    def __exit__(self, *exc_info: object) -> None:",
                "        self.close()",
            ]
        lines.append("")

    return "\n".join(lines)
