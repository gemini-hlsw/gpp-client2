"""
Per-environment operation pruning.

Nothing marks a selection as environment-specific by hand. Each operation is
pruned against each committed schema: a selection the schema cannot serve is
dropped, empty selection sets prune their parent recursively, fragments die
at a fixpoint, and unused variables are removed. A selection that survives in
no environment is a typo and fails the build; one that survives somewhere is
recorded in the availability manifest.
"""

from dataclasses import dataclass, field

from graphql.language import ast as gql_ast

from graphql import (
    DocumentNode,
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    GraphQLInterfaceType,
    GraphQLObjectType,
    GraphQLSchema,
    InlineFragmentNode,
    OperationDefinitionNode,
    SelectionSetNode,
    get_named_type,
)


@dataclass
class PruneResult:
    """Outcome of pruning the union document against one schema source."""

    document: DocumentNode
    dropped: list[tuple[str, str]]  # (Type.field, path)
    dead_fragments: set[str]
    dead_operations: list[str]
    operations: dict[str, OperationDefinitionNode] = field(default_factory=dict)
    fragments: dict[str, FragmentDefinitionNode] = field(default_factory=dict)


class _Pruner:
    """Prunes selections that a schema source cannot serve."""

    def __init__(self, schema: GraphQLSchema, dead_fragments: set[str]):
        self.schema = schema
        self.dead_fragments = dead_fragments
        self.dropped: list[tuple[str, str]] = []

    @staticmethod
    def _fields_of(parent_type):
        if isinstance(parent_type, (GraphQLObjectType, GraphQLInterfaceType)):
            return parent_type.fields
        return None

    def prune_selection_set(
        self, selection_set: SelectionSetNode | None, parent_type, path: list[str]
    ) -> SelectionSetNode | None:
        if selection_set is None:
            return None
        kept = []
        for selection in selection_set.selections:
            pruned = self._prune_selection(selection, parent_type, path)
            if pruned is not None:
                kept.append(pruned)
        if not kept:
            return None
        # A set reduced to just __typename survives: authors legitimately
        # probe a field's presence or concrete type that way (e.g. the GOATS
        # `opportunity { __typename }` selection), and an injected
        # discriminator left alone after pruning is harmless.
        return SelectionSetNode(selections=tuple(kept))

    def _prune_selection(self, selection, parent_type, path):
        if isinstance(selection, FieldNode):
            name = selection.name.value
            if name == "__typename":
                return selection
            fields = self._fields_of(parent_type)
            if fields is None or name not in fields:
                self.dropped.append(
                    (f"{parent_type.name}.{name}", ".".join([*path, name]))
                )
                return None
            field_def = fields[name]
            for argument in selection.arguments:
                if argument.name.value not in field_def.args:
                    self.dropped.append(
                        (
                            f"{parent_type.name}.{name}({argument.name.value}:)",
                            ".".join([*path, name]),
                        )
                    )
                    return None
            if selection.selection_set is None:
                return selection
            child_type = get_named_type(field_def.type)
            new_set = self.prune_selection_set(
                selection.selection_set, child_type, [*path, name]
            )
            if new_set is None:
                self.dropped.append(
                    (f"{parent_type.name}.{name}", ".".join([*path, name]))
                )
                return None
            return FieldNode(
                name=selection.name,
                alias=selection.alias,
                arguments=selection.arguments,
                directives=selection.directives,
                selection_set=new_set,
            )

        if isinstance(selection, InlineFragmentNode):
            condition = (
                selection.type_condition.name.value
                if selection.type_condition
                else None
            )
            target = self.schema.type_map.get(condition) if condition else parent_type
            if target is None:
                self.dropped.append((f"...on {condition}", ".".join(path)))
                return None
            new_set = self.prune_selection_set(
                selection.selection_set, target, [*path, f"...{condition}"]
            )
            if new_set is None:
                return None
            return InlineFragmentNode(
                type_condition=selection.type_condition,
                directives=selection.directives,
                selection_set=new_set,
            )

        if isinstance(selection, FragmentSpreadNode):
            if selection.name.value in self.dead_fragments:
                return None
            return selection

        return selection


def _collect_spreads(node) -> set[str]:
    """Collect fragment spread names reachable from an AST node."""
    names: set[str] = set()
    if isinstance(node, FragmentSpreadNode):
        names.add(node.name.value)
    for attribute in ("selections", "selection_set"):
        value = getattr(node, attribute, None)
        if isinstance(value, (tuple, list)):
            for child in value:
                names |= _collect_spreads(child)
        elif value is not None and hasattr(value, "selections"):
            names |= _collect_spreads(value)
    return names


def collect_transitive_spreads(node, fragments) -> set[str]:
    """Collect fragment spreads reachable from a node, following fragments."""
    seen: set[str] = set()
    frontier = _collect_spreads(node)
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        fragment = fragments.get(name)
        if fragment is not None:
            frontier |= _collect_spreads(fragment.selection_set)
    return seen


def _collect_variable_names(node) -> set[str]:
    """Collect every variable name referenced anywhere under an AST node."""
    names: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, gql_ast.VariableNode):
            names.add(current.name.value)
        for key in getattr(current, "keys", ()):
            if key == "loc":
                continue
            value = getattr(current, key, None)
            if isinstance(value, gql_ast.Node):
                stack.append(value)
            elif isinstance(value, (tuple, list)):
                stack.extend(v for v in value if isinstance(v, gql_ast.Node))
    return names


def prune_document_for_schema(
    document: DocumentNode, schema: GraphQLSchema
) -> PruneResult:
    """
    Prune every operation and fragment against one schema source.

    Fragment death reaches a fixpoint: a fragment dies when its type condition
    is unknown or all of its selections prune away, and spreads of dead
    fragments are then dropped, which can empty further fragments.
    """
    fragments = {
        d.name.value: d
        for d in document.definitions
        if isinstance(d, FragmentDefinitionNode)
    }

    dead_fragments: set[str] = set()
    while True:
        newly_dead: set[str] = set()
        for name, fragment in fragments.items():
            if name in dead_fragments:
                continue
            condition_type = schema.type_map.get(fragment.type_condition.name.value)
            if condition_type is None:
                newly_dead.add(name)
                continue
            probe = _Pruner(schema, dead_fragments)
            if (
                probe.prune_selection_set(
                    fragment.selection_set, condition_type, [name]
                )
                is None
            ):
                newly_dead.add(name)
        if not newly_dead:
            break
        dead_fragments |= newly_dead

    pruner = _Pruner(schema, dead_fragments)
    kept_definitions = []
    dead_operations: list[str] = []
    operations: dict[str, OperationDefinitionNode] = {}
    pruned_fragments: dict[str, FragmentDefinitionNode] = {}

    root_types = {
        "query": schema.query_type,
        "mutation": schema.mutation_type,
        "subscription": schema.subscription_type,
    }

    for definition in document.definitions:
        if isinstance(definition, FragmentDefinitionNode):
            if definition.name.value in dead_fragments:
                continue
            condition_type = schema.type_map[definition.type_condition.name.value]
            new_set = pruner.prune_selection_set(
                definition.selection_set, condition_type, [definition.name.value]
            )
            pruned = FragmentDefinitionNode(
                name=definition.name,
                type_condition=definition.type_condition,
                variable_definitions=definition.variable_definitions,
                directives=definition.directives,
                selection_set=new_set,
            )
            kept_definitions.append(pruned)
            pruned_fragments[definition.name.value] = pruned
        elif isinstance(definition, OperationDefinitionNode):
            operation_name = definition.name.value if definition.name else "<anonymous>"
            root_type = root_types[definition.operation.value]
            new_set = pruner.prune_selection_set(
                definition.selection_set, root_type, [operation_name]
            )
            if new_set is None:
                dead_operations.append(operation_name)
                continue
            pruned_operation = OperationDefinitionNode(
                name=definition.name,
                operation=definition.operation,
                variable_definitions=definition.variable_definitions,
                directives=definition.directives,
                selection_set=new_set,
            )
            # Drop variable definitions left unused by pruning.
            used = _collect_variable_names(new_set)
            for spread in sorted(collect_transitive_spreads(new_set, pruned_fragments)):
                fragment = pruned_fragments.get(spread)
                if fragment is not None:
                    used |= _collect_variable_names(fragment.selection_set)
            pruned_operation.variable_definitions = tuple(
                v
                for v in pruned_operation.variable_definitions
                if v.variable.name.value in used
            )
            kept_definitions.append(pruned_operation)
            operations[operation_name] = pruned_operation

    return PruneResult(
        document=DocumentNode(definitions=tuple(kept_definitions)),
        dropped=pruner.dropped,
        dead_fragments=dead_fragments,
        dead_operations=dead_operations,
        operations=operations,
        fragments=pruned_fragments,
    )
