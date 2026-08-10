"""Schema merge unit tests."""

from codegen.schema import merge_schema_documents
from graphql import parse, print_ast


def merge(newest: str, oldest: str):
    documents = {"development": parse(newest), "production": parse(oldest)}
    return merge_schema_documents(documents, ["development", "production"])


def rendered(document) -> str:
    return print_ast(document)


def test_union_of_types_and_fields():
    merged, divergences = merge(
        "type Query { a: Int } type OnlyDev { x: Int }",
        "type Query { a: Int, b: String } type OnlyProd { y: Int }",
    )
    text = rendered(merged)
    assert "OnlyDev" in text and "OnlyProd" in text
    assert "b: String" in text
    assert divergences == []


def test_nullability_relaxes_to_nullable():
    merged, divergences = merge(
        "type Query { a: Int! }",
        "type Query { a: Int }",
    )
    assert "a: Int\n" in rendered(merged) or "a: Int\n}" in rendered(merged)
    assert [d.kind for d in divergences] == ["nullability"]


def test_structural_divergence_keeps_newest_and_records():
    merged, divergences = merge(
        "type Query { a: [NewEnum!] } enum NewEnum { X }",
        "type Query { a: [OldEnum!] } enum OldEnum { X }",
    )
    assert "a: [NewEnum!]" in rendered(merged)
    assert [d.kind for d in divergences] == ["structural"]
    assert divergences[0].location == "Query.a"


def test_enum_values_union():
    merged, _ = merge(
        "type Query { a: E } enum E { NEW SHARED }",
        "type Query { a: E } enum E { SHARED OLD }",
    )
    text = rendered(merged)
    assert "NEW" in text and "OLD" in text and text.count("SHARED") == 1


def test_description_backfill_from_older_source():
    merged, _ = merge(
        "type Query { a: Int }",
        '"""Query docs""" type Query { """field docs""" a: Int }',
    )
    text = rendered(merged)
    assert "Query docs" in text
    assert "field docs" in text


def test_inputs_merge_fields():
    merged, _ = merge(
        "type Query { a: Int } input I { x: Int }",
        "type Query { a: Int } input I { x: Int, y: String }",
    )
    assert "y: String" in rendered(merged)


def test_source_documents_not_mutated():
    """Merging must never corrupt the per-source documents used for pruning."""
    dev = parse("type Query { a: Int }")
    prod = parse("type Query { a: Int, prodOnly: ProdType } type ProdType { z: Int }")
    before = print_ast(dev)
    merge_schema_documents(
        {"development": dev, "production": prod}, ["development", "production"]
    )
    assert print_ast(dev) == before
