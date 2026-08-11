"""
Operations tree loading, validation, and __typename injection.

There is one operations tree containing the union of every selection used in
any environment. The directory an operation file lives in names its domain;
directories starting with an underscore hold shared fragments only.
"""

from dataclasses import dataclass
from pathlib import Path

from graphql.validation import NoUnusedFragmentsRule, specified_rules

from gqlforge import GqlforgeError
from gqlforge.config import Config
from graphql import (
    DocumentNode,
    FieldNode,
    FragmentDefinitionNode,
    GraphQLInterfaceType,
    GraphQLSchema,
    GraphQLUnionType,
    InlineFragmentNode,
    NameNode,
    OperationDefinitionNode,
    SelectionSetNode,
    get_named_type,
    parse,
    validate,
)


@dataclass
class LoadedOperations:
    """The union operations document plus provenance metadata."""

    document: DocumentNode
    domains: dict[str, str]  # operation name -> domain directory name
    docs: dict[str, str]  # operation name -> leading comment block


def find_operation_files(config: Config) -> list[Path]:
    """Every operations file, sorted; empty when there is no tree."""
    if not config.operations_dir.is_dir():
        return []
    return sorted(
        p
        for pattern in ("*.graphql", "*.gql")
        for p in config.operations_dir.rglob(pattern)
        if p.is_file()
    )


def _leading_comment(lines: list[str], start_line: int) -> str | None:
    """
    The contiguous ``#`` comment block directly above ``start_line``
    (1-based), or None. A blank line breaks contiguity, so a file header
    separated by one blank line never becomes a docstring.
    """
    collected: list[str] = []
    index = start_line - 2
    while index >= 0 and lines[index].lstrip().startswith("#"):
        text = lines[index].lstrip()[1:]
        collected.append(text[1:] if text.startswith(" ") else text)
        index -= 1
    if not collected:
        return None
    return "\n".join(reversed(collected)).strip() or None


def load_operations(config: Config) -> LoadedOperations:
    """Parse every operations file and record each operation's domain."""
    files = find_operation_files(config)
    if not files:
        raise GqlforgeError(f"No operation files found under {config.operations_dir}")

    definitions = []
    domains: dict[str, str] = {}
    docs: dict[str, str] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        try:
            document = parse(text)
        except Exception as exc:
            raise GqlforgeError(f"Failed to parse {path}\n{exc}") from exc
        lines = text.splitlines()
        relative = path.relative_to(config.operations_dir)
        # Files at the tree root form the anonymous domain "" - the
        # no-domains layout, emitted as plain (Async)Operations classes.
        domain = relative.parts[0] if len(relative.parts) > 1 else ""
        for definition in document.definitions:
            definitions.append(definition)
            if isinstance(definition, OperationDefinitionNode):
                if definition.name is None:
                    raise GqlforgeError(f"Anonymous operation in {path}.")
                name = definition.name.value
                if name in domains:
                    raise GqlforgeError(f"Duplicate operation name '{name}'.")
                if domain.startswith("_"):
                    raise GqlforgeError(
                        f"Operation '{name}' lives in '{relative}', but "
                        "underscore-prefixed directories hold shared "
                        "fragments only."
                    )
                domains[name] = domain
                if definition.loc is not None:
                    doc = _leading_comment(lines, definition.loc.start_token.line)
                    if doc:
                        docs[name] = doc

    return LoadedOperations(
        document=DocumentNode(definitions=tuple(definitions)),
        domains=domains,
        docs=docs,
    )


def validate_operations(schema: GraphQLSchema, document: DocumentNode) -> list[str]:
    """
    Validate a document against a schema, ignoring unused-fragment errors.

    Fragments are shared across files, so the concatenated document may hold
    fragments used only by other environments' pruned outputs.
    """
    rules = [r for r in specified_rules if r is not NoUnusedFragmentsRule]
    return [e.message for e in validate(schema, document, rules=rules)]


def inject_typename(document: DocumentNode, schema: GraphQLSchema) -> DocumentNode:
    """
    Add ``__typename`` to every selection set on an interface or union type.

    Response models for abstract types are discriminated unions keyed on
    ``__typename``; injecting it here means operation authors never have to
    remember it, and parsing is deterministic.
    """

    def rewrite(
        selection_set: SelectionSetNode | None, parent_type
    ) -> SelectionSetNode | None:
        if selection_set is None or parent_type is None:
            return selection_set
        selections = []
        for selection in selection_set.selections:
            if isinstance(selection, FieldNode):
                if selection.name.value == "__typename":
                    selections.append(selection)
                    continue
                fields = getattr(parent_type, "fields", None) or {}
                field_def = fields.get(selection.name.value)
                child_type = (
                    get_named_type(field_def.type) if field_def is not None else None
                )
                selections.append(
                    FieldNode(
                        name=selection.name,
                        alias=selection.alias,
                        arguments=selection.arguments,
                        directives=selection.directives,
                        selection_set=rewrite(selection.selection_set, child_type),
                    )
                )
            elif isinstance(selection, InlineFragmentNode):
                target = (
                    schema.type_map.get(selection.type_condition.name.value)
                    if selection.type_condition
                    else parent_type
                )
                selections.append(
                    InlineFragmentNode(
                        type_condition=selection.type_condition,
                        directives=selection.directives,
                        selection_set=rewrite(selection.selection_set, target),
                    )
                )
            else:
                selections.append(selection)

        needs_typename = isinstance(
            parent_type, (GraphQLInterfaceType, GraphQLUnionType)
        ) and not any(
            isinstance(s, FieldNode) and s.name.value == "__typename"
            for s in selections
        )
        if needs_typename:
            selections.insert(
                0,
                FieldNode(
                    name=NameNode(value="__typename"),
                    arguments=(),
                    directives=(),
                ),
            )
        return SelectionSetNode(selections=tuple(selections))

    root_types = {
        "query": schema.query_type,
        "mutation": schema.mutation_type,
        "subscription": schema.subscription_type,
    }

    definitions = []
    for definition in document.definitions:
        if isinstance(definition, OperationDefinitionNode):
            definitions.append(
                OperationDefinitionNode(
                    name=definition.name,
                    operation=definition.operation,
                    variable_definitions=definition.variable_definitions,
                    directives=definition.directives,
                    selection_set=rewrite(
                        definition.selection_set,
                        root_types[definition.operation.value],
                    ),
                )
            )
        elif isinstance(definition, FragmentDefinitionNode):
            definitions.append(
                FragmentDefinitionNode(
                    name=definition.name,
                    type_condition=definition.type_condition,
                    variable_definitions=definition.variable_definitions,
                    directives=definition.directives,
                    selection_set=rewrite(
                        definition.selection_set,
                        schema.type_map.get(definition.type_condition.name.value),
                    ),
                )
            )
        else:
            definitions.append(definition)

    return DocumentNode(definitions=tuple(definitions))
