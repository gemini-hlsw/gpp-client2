"""Pruning unit tests."""

from gqlforge.prune import prune_document_for_schema
from graphql import build_schema, parse, print_ast

SCHEMA_FULL = build_schema(
    """
    type Query { thing: Thing, devOnly: Detail }
    type Thing { a: Int, b: Int, detail: Detail }
    type Detail { x: Int, y: Int }
    """
)

SCHEMA_NARROW = build_schema(
    """
    type Query { thing: Thing }
    type Thing { a: Int }
    """
)


def prune(text: str, schema):
    return prune_document_for_schema(parse(text), schema)


def test_prunes_unknown_field():
    result = prune("query Q { thing { a b } }", SCHEMA_NARROW)
    text = print_ast(result.document)
    assert "b" not in text
    assert ("Thing.b", "Q.thing.b") in result.dropped


def test_empty_selection_prunes_parent_recursively():
    result = prune("query Q { thing { detail { x } } }", SCHEMA_NARROW)
    assert result.dead_operations == ["Q"]


def test_dead_operation_when_root_empties():
    result = prune("query Q { devOnly { x } }", SCHEMA_NARROW)
    assert result.dead_operations == ["Q"]


def test_fragment_death_fixpoint():
    text = """
    query Q { thing { a ...DetailBits } }
    fragment DetailBits on Thing { detail { ...Inner } }
    fragment Inner on Detail { x }
    """
    result = prune(text, SCHEMA_NARROW)
    assert result.dead_fragments == {"DetailBits", "Inner"}
    rendered = print_ast(result.document)
    assert "DetailBits" not in rendered
    assert result.operations["Q"] is not None


def test_unused_variables_dropped():
    text = """
    query Q($keep: Int, $drop: Int) {
      thing { a(unused: $drop) b }
    }
    """
    schema = build_schema(
        "type Query { thing: Thing } type Thing { a(used: Int): Int, b: Int }"
    )
    result = prune(text.replace("unused: $drop", "used: $keep"), schema)
    operation = result.operations["Q"]
    names = [v.variable.name.value for v in operation.variable_definitions]
    assert names == ["keep"]


def test_unknown_argument_prunes_field():
    schema = build_schema("type Query { thing(known: Int): Int }")
    result = prune("query Q { thing(unknown: 1) }", schema)
    assert result.dead_operations == ["Q"]
    assert any("unknown" in location for location, _ in result.dropped)


def test_typename_only_selection_survives():
    # Authors probe presence/concrete type with bare __typename (GOATS does);
    # it must not count as an empty selection set.
    result = prune("query Q { thing { detail { __typename } } }", SCHEMA_FULL)
    assert result.dead_operations == []
    assert "__typename" in print_ast(result.document)


def test_full_schema_keeps_everything():
    result = prune("query Q { thing { a b detail { x y } } }", SCHEMA_FULL)
    assert result.dropped == []
    assert result.dead_operations == []
