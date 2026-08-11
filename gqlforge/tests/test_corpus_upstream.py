"""Nightly canary: the corpus, against live upstream schemas.

The committed snapshots in ``schemas/`` catch our regressions; this
module catches the other direction - upstream APIs evolving shapes the
emitters have not met yet. Failure semantics are deliberate: an
unreachable endpoint or malformed introspection response *skips* (that
is network noise, not a gqlforge bug), while a schema that fetches
cleanly but fails generation or import *fails* (that is the signal).

Marked ``upstream`` and deselected by default; the corpus-canary
workflow runs it nightly with ``pytest -m upstream``.
"""

import httpx
import pytest
from support import importable, make_consumer
from test_corpus import CORPUS

from gqlforge.pipeline import run_generate
from graphql import build_client_schema, get_introspection_query, print_schema

pytestmark = pytest.mark.upstream

INTROSPECTION_ENDPOINTS = {
    "countries": "https://countries.trevorblades.com/",
    "rickandmorty": "https://rickandmortyapi.com/graphql",
    "swapi": "https://swapi-graphql.netlify.app/graphql",
    "anilist": "https://graphql.anilist.co",
}
SDL_URLS = {
    "github": "https://docs.github.com/public/fpt/schema.docs.graphql",
}


def _fetch_sdl(name: str) -> str:
    try:
        if name in SDL_URLS:
            response = httpx.get(SDL_URLS[name], timeout=60, follow_redirects=True)
            response.raise_for_status()
            return response.text
        response = httpx.post(
            INTROSPECTION_ENDPOINTS[name],
            json={"query": get_introspection_query()},
            timeout=60,
            follow_redirects=True,
        )
        response.raise_for_status()
        return print_schema(build_client_schema(response.json()["data"]))
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        pytest.skip(f"upstream fetch for '{name}' failed: {exc!r}")


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_upstream_generates_importable_models(tmp_path, name):
    sdl = _fetch_sdl(name)
    package = f"upstream_{name}"
    config = make_consumer(tmp_path, package, {"main": sdl}, ["main"], vendored=True)
    run_generate(config)

    with importable(tmp_path, package) as import_module:
        for module in ("scalars", "enums", "inputs", "models"):
            import_module(f"_generated.{module}")
        models = import_module("_generated.models")
        model_cls = getattr(models, CORPUS[name])
        instance = model_cls()
        field = next(f for f in model_cls.model_fields if f != "typename")
        assert repr(getattr(instance, field)) == "UNSET"
