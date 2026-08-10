"""
Schema loading, merging, and downloading.

The merged schema is the union of every committed environment schema: union
of types, union of fields per type, union of enum values. Nullability
differences relax to the nullable form; structural differences are recorded
and become fatal only when an operation actually selects them.
"""

import copy
from collections.abc import Iterable
from dataclasses import dataclass, field

from graphql.language import ast as gql_ast

from codegen import SCHEMAS_DIR, SOURCE_ORDER, CodegenError
from graphql import (
    DocumentNode,
    GraphQLSchema,
    ListTypeNode,
    NamedTypeNode,
    NonNullTypeNode,
    TypeNode,
    build_ast_schema,
    build_client_schema,
    get_introspection_query,
    parse,
    print_ast,
    print_schema,
)


def discover_sources() -> list[str]:
    """Return committed schema sources ordered newest-first."""
    sources = [s for s in SOURCE_ORDER if (SCHEMAS_DIR / f"{s}.graphql").is_file()]
    if not sources:
        raise CodegenError(f"No schema files found under {SCHEMAS_DIR}")
    return sources


def load_schema_document(source: str) -> DocumentNode:
    """Parse a committed schema SDL file into an AST document."""
    return parse((SCHEMAS_DIR / f"{source}.graphql").read_text(encoding="utf-8"))


def build_schema(document: DocumentNode) -> GraphQLSchema:
    """Build an (assumed valid) executable schema from an SDL document."""
    return build_ast_schema(document, assume_valid=True)


def download_schema_sdl(base_url: str, token: str, timeout: float = 60.0) -> str:
    """
    Download a deployment's schema via introspection and return SDL text.

    Parameters
    ----------
    base_url : str
        Base URL of the deployment (the ``/odb`` path is appended).
    token : str
        Bearer token used for the introspection request.
    timeout : float
        Request timeout in seconds.
    """
    import httpx

    introspection = get_introspection_query(
        descriptions=True,
        specified_by_url=True,
        directive_is_repeatable=True,
        input_value_deprecation=True,
        input_object_one_of=True,
    )
    response = httpx.post(
        base_url.rstrip("/") + "/odb",
        json={"query": introspection},
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise CodegenError(
            f"Introspection against {base_url} failed with HTTP "
            f"{response.status_code}: {response.text[:500]}"
        )
    payload = response.json()
    if payload.get("errors"):
        raise CodegenError(f"Introspection errors: {payload['errors']}")
    schema = build_client_schema(payload["data"])
    return print_schema(schema) + "\n"


@dataclass
class Divergence:
    """A field whose type differs between schema sources."""

    kind: str  # "nullability" or "structural"
    location: str  # "Type.field"
    types: dict[str, str] = field(default_factory=dict)  # source -> printed type


def _relax_nullability(a: TypeNode, b: TypeNode) -> TypeNode | None:
    """
    Merge two type nodes that differ only in nullability.

    Keeps NonNull only at levels where both sides have it. Returns ``None``
    when the difference is structural (different named types or shapes).
    """
    a_nonnull = isinstance(a, NonNullTypeNode)
    b_nonnull = isinstance(b, NonNullTypeNode)
    inner_a = a.type if a_nonnull else a
    inner_b = b.type if b_nonnull else b

    merged: TypeNode
    if isinstance(inner_a, ListTypeNode) and isinstance(inner_b, ListTypeNode):
        inner = _relax_nullability(inner_a.type, inner_b.type)
        if inner is None:
            return None
        merged = ListTypeNode(type=inner)
    elif (
        isinstance(inner_a, NamedTypeNode)
        and isinstance(inner_b, NamedTypeNode)
        and inner_a.name.value == inner_b.name.value
    ):
        merged = inner_a
    else:
        return None

    if a_nonnull and b_nonnull:
        return NonNullTypeNode(type=merged)
    return merged


_FIELD_CONTAINER_KINDS = (
    gql_ast.ObjectTypeDefinitionNode,
    gql_ast.InterfaceTypeDefinitionNode,
)


def merge_schema_documents(
    documents: dict[str, DocumentNode],
    order: list[str],
) -> tuple[DocumentNode, list[Divergence]]:
    """
    Merge schema documents into a union schema.

    Parameters
    ----------
    documents : dict[str, DocumentNode]
        SDL documents keyed by source name.
    order : list[str]
        Source names ordered newest-first. The newest source is the base;
        older sources contribute anything the base lacks, including
        descriptions the newest source dropped.

    Returns
    -------
    tuple[DocumentNode, list[Divergence]]
        The merged document and every type divergence found. Structural
        divergences keep the newest source's definition.

    Notes
    -----
    The input documents are never mutated. The base is deep-copied first:
    grafting an older source's field into a shared node would otherwise
    corrupt the per-source schemas used for pruning.
    """
    base_source = order[0]
    divergences: list[Divergence] = []

    merged_defs = list(copy.deepcopy(documents[base_source]).definitions)
    merged_by_name = {
        d.name.value: d for d in merged_defs if hasattr(d, "name") and d.name
    }

    for source in order[1:]:
        for definition in documents[source].definitions:
            name = getattr(getattr(definition, "name", None), "value", None)
            if name is None:
                continue  # schema definition node: keep base's
            base_def = merged_by_name.get(name)
            if base_def is None:
                merged_defs.append(definition)
                merged_by_name[name] = definition
                continue
            _merge_definition(base_def, definition, base_source, source, divergences)

    return DocumentNode(definitions=tuple(merged_defs)), divergences


def _backfill_description(base_node: gql_ast.Node, other_node: gql_ast.Node) -> None:
    """Adopt the older source's description when the base has none."""
    if getattr(base_node, "description", None) is None and (
        getattr(other_node, "description", None) is not None
    ):
        base_node.description = other_node.description  # type: ignore[attr-defined]


def _merge_definition(base_def, other_def, base_source, other_source, divergences):
    """Merge one older definition into the base definition in place."""
    _backfill_description(base_def, other_def)
    type_name = base_def.name.value

    if (
        isinstance(base_def, _FIELD_CONTAINER_KINDS)
        and isinstance(other_def, _FIELD_CONTAINER_KINDS)
    ) or (
        isinstance(base_def, gql_ast.InputObjectTypeDefinitionNode)
        and isinstance(other_def, gql_ast.InputObjectTypeDefinitionNode)
    ):
        base_def.fields = _merge_field_lists(
            type_name,
            base_def.fields,
            other_def.fields,
            base_source,
            other_source,
            divergences,
        )
    elif isinstance(base_def, gql_ast.EnumTypeDefinitionNode) and isinstance(
        other_def, gql_ast.EnumTypeDefinitionNode
    ):
        by_name = {v.name.value: v for v in base_def.values}
        additions = []
        for value in other_def.values:
            existing = by_name.get(value.name.value)
            if existing is None:
                additions.append(value)
            else:
                _backfill_description(existing, value)
        if additions:
            base_def.values = tuple(base_def.values) + tuple(additions)
    elif isinstance(base_def, gql_ast.UnionTypeDefinitionNode) and isinstance(
        other_def, gql_ast.UnionTypeDefinitionNode
    ):
        existing = {t.name.value for t in base_def.types}
        additions = [t for t in other_def.types if t.name.value not in existing]
        if additions:
            base_def.types = tuple(base_def.types) + tuple(additions)
    # Scalars, directives, and everything else: keep the base definition.


def _merge_field_lists(
    type_name, base_fields, other_fields, base_source, other_source, divergences
):
    """Merge two field lists, unioning fields and relaxing nullability."""
    merged = list(base_fields)
    by_name = {f.name.value: (i, f) for i, f in enumerate(merged)}

    for other_field in other_fields:
        field_name = other_field.name.value
        entry = by_name.get(field_name)
        if entry is None:
            merged.append(other_field)
            continue
        index, base_field = entry
        _backfill_description(base_field, other_field)
        if print_ast(base_field.type) == print_ast(other_field.type):
            continue
        relaxed = _relax_nullability(base_field.type, other_field.type)
        location = f"{type_name}.{field_name}"
        rendered = {
            base_source: print_ast(base_field.type),
            other_source: print_ast(other_field.type),
        }
        if relaxed is None:
            divergences.append(
                Divergence(kind="structural", location=location, types=rendered)
            )
            continue  # structural: keep the newest definition
        divergences.append(
            Divergence(kind="nullability", location=location, types=rendered)
        )
        base_field.type = relaxed
        merged[index] = base_field

    return tuple(merged)


def field_availability(
    schemas: dict[str, GraphQLSchema], sources: Iterable[str]
) -> dict[str, tuple[str, ...]]:
    """Map every Type.field not present everywhere to the sources that have it."""
    sources = list(sources)
    per_source: dict[str, set[str]] = {}
    for source in sources:
        pairs = set()
        for type_name, graphql_type in schemas[source].type_map.items():
            if type_name.startswith("__"):
                continue
            for field_name in getattr(graphql_type, "fields", None) or {}:
                pairs.add(f"{type_name}.{field_name}")
        per_source[source] = pairs

    every = set().union(*per_source.values())
    availability = {}
    for pair in sorted(every):
        present = tuple(s for s in sources if pair in per_source[s])
        if len(present) != len(sources):
            availability[pair] = present
    return availability
