"""Corpus tests: real public GraphQL schemas, end to end.

Each snapshot in ``schemas/`` (see its README for provenance) must
survive the whole journey: generation, then *importing* the emitted
modules against a minimal runtime, then instantiating a model - so
emitter bugs that pydantic would reject (bad annotations, name
collisions, reserved words) fail here instead of in a consumer.
"""

import json
from pathlib import Path

import pytest
from support import importable, make_consumer

from gqlforge.pipeline import run_generate
from graphql import parse, print_ast

SCHEMAS_DIR = Path(__file__).parent / "schemas"

# Fixture name -> a well-known type expected in the generated models.
CORPUS = {
    "countries": "Country",
    "rickandmorty": "Character",
    "swapi": "Film",
    "anilist": "Media",
    "github": "Repository",
}


def _fixture(name: str) -> str:
    return (SCHEMAS_DIR / f"{name}.graphql").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_generates_importable_models(tmp_path, name):
    package = f"corpus_{name}"
    config = make_consumer(tmp_path, package, {"main": _fixture(name)}, ["main"])
    run_generate(config)

    with importable(tmp_path, package) as import_module:
        for module in ("scalars", "enums", "inputs", "models"):
            import_module(f"_generated.{module}")
        models = import_module("_generated.models")
        model_cls = getattr(models, CORPUS[name])
        # Every field defaults to UNSET, so a bare construction must work
        # and echo the sentinel back.
        instance = model_cls()
        field = next(f for f in model_cls.model_fields if f != "typename")
        assert repr(getattr(instance, field)) == "UNSET"


def test_full_pipeline_on_flat_operations(tmp_path):
    operations = """\
# Look up a single country by its ISO 3166-1 alpha-2 code.
query getCountryByCode($code: ID!) {
  country(code: $code) {
    code
    name
    emoji
  }
}

query getCountries {
  countries {
    code
    name
  }
}
"""
    package = "corpus_pipeline"
    config = make_consumer(
        tmp_path,
        package,
        {"main": _fixture("countries")},
        ["main"],
        operations=operations,
    )
    run_generate(config)

    with importable(tmp_path, package) as import_module:
        domains = import_module("_generated.domains")
        operation_map = import_module("_generated.operations")

        # Root-level files form the anonymous domain: plain class names,
        # method names keeping their resource.
        for class_name in ("Operations", "AsyncOperations"):
            cls = getattr(domains, class_name)
            assert callable(cls.get_country_by_code)
            assert callable(cls.get_countries)
        # The leading comment block is the docstring.
        assert "ISO 3166-1" in domains.Operations.get_country_by_code.__doc__
        assert "emoji" in operation_map.OPERATION_TEXT["getCountryByCode"]["main"]


def test_prunes_field_missing_from_one_source(tmp_path):
    """Two sources derived from one real schema must prune precisely."""
    newest = _fixture("rickandmorty")
    document = parse(newest)
    stripped = 0
    for definition in document.definitions:
        if getattr(definition, "name", None) and definition.name.value == "Character":
            kept = tuple(f for f in definition.fields if f.name.value != "gender")
            stripped = len(definition.fields) - len(kept)
            definition.fields = kept
    assert stripped == 1, "fixture drifted: Character.gender not found"
    oldest = print_ast(document)

    operations = """\
query getCharacterById($id: ID!) {
  character(id: $id) {
    id
    name
    gender
  }
}
"""
    package = "corpus_prune"
    config = make_consumer(
        tmp_path,
        package,
        {"development": newest, "production": oldest},
        ["development", "production"],
        operations=operations,
    )
    run_generate(config)

    with importable(tmp_path, package) as import_module:
        operation_map = import_module("_generated.operations")
        texts = operation_map.OPERATION_TEXT["getCharacterById"]
        assert "gender" in texts["development"]
        assert "gender" not in texts["production"]

    manifest = json.loads((tmp_path / "availability.json").read_text())
    assert manifest["fields"]["Character.gender"] == ["development"]
    assert manifest["operations"]["getCharacterById"] == [
        "development",
        "production",
    ]
