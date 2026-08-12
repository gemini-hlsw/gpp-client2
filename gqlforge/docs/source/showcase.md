# Showcase: a real API, end to end

The [Rick and Morty API](https://rickandmortyapi.com/graphql) is a public
GraphQL endpoint that needs no token, which makes it the shortest possible
proof that gqlforge's output really runs: two committed files in, a typed
client out, live data back.

Everything on this page is regenerated **at docs build time** by running
the installed pipeline over the committed schema snapshot from gqlforge's
[test corpus](https://github.com/gemini-hlsw/gpp-client2/tree/main/gqlforge/tests/schemas).
The generated code you see below is not pasted by hand - it cannot drift
from the emitters.

## The inputs

A `[tool.gqlforge]` table with no `runtime_package`, so gqlforge vendors
the runtime and emits the default client ({doc}`configuration`):

```toml
[tool.gqlforge]
schemas = "schemas"                  # schemas/rickandmorty.graphql
operations = "operations"
output = "src/ram/_generated"
merged_schema = "schemas/merged.graphql"
availability = "availability.json"
source_order = ["rickandmorty"]
generated_package = "ram._generated"
```

And one operations file. The directory it sits in (`operations/character/`)
becomes the client attribute; the `#` comments become the generated
method docstrings ({doc}`docstrings`); the operation names follow the
`<verb><Resource>[By<Key>]` convention that derives method names:

```{literalinclude} _showcase/operations/character/queries.graphql
:language: graphql
```

## Generate

```{literalinclude} _showcase/gen/generate.log
:language: console
```

(A custom scalar gqlforge does not recognize, like this API's `Upload`,
maps to `str` with a warning - nothing blocks.)

## What came out

One pydantic model per schema type, every field defaulting to `UNSET` so
"not selected by your operation" stays distinct from a server-returned
null:

```{literalinclude} _showcase/gen/_generated/models.py
:pyobject: Character
```

One domain class per operations directory - `getCharacterById` became
`get_by_id`, with the comment flowing into the docstring and the GraphQL
variables typed out:

```{literalinclude} _showcase/gen/_generated/domains.py
:pyobject: CharacterOperations.get_by_id
```

`getCharacters` became `get_all(page=..., filter=...)` on the same class,
and `AsyncCharacterOperations` mirrors everything as coroutines. The
vendored runtime (`_base.py`, `_executor.py`, `_ws.py`, `_exceptions.py`)
and a ready `Client`/`AsyncClient` land next to them.

## Run it

This is the complete program - no hand-written runtime, no other
dependencies beyond what the generated package imports:

```python
from ram._generated.client import Client
from ram._generated.inputs import FilterCharacter

with Client("https://rickandmortyapi.com/graphql") as api:
    rick = api.character.get_by_id("1")
    print(repr(rick))

    page = api.character.get_all(
        filter=FilterCharacter(species="Human", status="Alive")
    )
    print(page.info.count, "matches;", [c.name for c in page.results[:3]])
```

Against the live API this prints (captured 2026-08-11):

```console
Character(id='1', name='Rick Sanchez', status='Alive', species='Human', location=Location(name='Citadel of Ricks', dimension='unknown'), image='https://rickandmortyapi.com/api/character/avatar/1.jpeg')
245 matches; ['Rick Sanchez', 'Morty Smith', 'Summer Smith']
```

Note what the `repr` shows: only the fields the operation selected.
`rick.gender` exists on the model and type-checks, but the query never
asked for it, so at runtime it is `UNSET` - falsy, and distinct from
`None`.

## And when the schema is huge

Legibility is why this page uses a 200-line schema. For scale, the same
test corpus includes the full **GitHub GraphQL schema** - 1.5 MB of SDL
producing roughly 1,300 model classes - and the test suite generates it
and imports the result on every run. There is nothing to configure
differently; it is just more of the same output than anyone would want to
read on a docs page.

Where gqlforge really earns its keep, though, is not one schema but
several versions of one API - see {doc}`index` for the multi-source
story and {doc}`configuration` for wiring it up.
