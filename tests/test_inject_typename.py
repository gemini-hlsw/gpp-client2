"""__typename injection unit tests."""

from codegen.operations import inject_typename
from graphql import build_schema, parse, print_ast

SCHEMA = build_schema(
    """
    type Query { pet: Pet, house: House }
    union Pet = Cat | Dog
    type Cat { name: String }
    type Dog { name: String }
    type House { door: String }
    interface Shape { area: Int }
    """
)


def test_injects_into_union_selection():
    document = inject_typename(parse("query Q { pet { ... on Cat { name } } }"), SCHEMA)
    assert "__typename" in print_ast(document)


def test_idempotent_when_already_present():
    document = inject_typename(
        parse("query Q { pet { __typename ... on Cat { name } } }"), SCHEMA
    )
    assert print_ast(document).count("__typename") == 1


def test_object_selections_untouched():
    document = inject_typename(parse("query Q { house { door } }"), SCHEMA)
    assert "__typename" not in print_ast(document)
