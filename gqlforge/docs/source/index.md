# gqlforge

`gqlforge` generates a typed Python client from GraphQL. Its specialty is
an API deployed in several environments whose schemas differ: you write
each query once, and `gqlforge` derives a per-environment version of it -
so one installed package talks to development, staging, or production,
chosen at runtime.

It is also a perfectly ordinary single-schema codegen, and a
models-only generator for projects that just want pydantic types (see
{doc}`domains`).

## Quickstart

Three files and no hand-written runtime:

```toml
# pyproject.toml
[tool.gqlforge]
schemas = "schemas"                  # schemas/main.graphql lives here
operations = "operations"
output = "src/myclient/_generated"
merged_schema = "schemas/merged.graphql"
availability = "availability.json"
source_order = ["main"]
generated_package = "myclient._generated"
```

Drop your SDL in `schemas/main.graphql`, a query in `operations/`, run
`gqlforge generate`, and use the client it emitted:

```python
from myclient._generated.client import Client

with Client("https://api.example.com/graphql", token="...") as api:
    widget = api.ops.get_widget_by_id(id="w-1")
    print(widget.name)  # typed pydantic model; unselected -> UNSET
```

Sync and async clients, typed models, subscriptions over
graphql-transport-ws, and a raw `api.graphql(...)` escape hatch - all
generated. ({doc}`configuration` covers bring-your-own-runtime for
curated clients.)

## How it works

1. Commit one SDL file per schema source, and write each GraphQL
   operation once - selecting the union of everything you use anywhere.
2. `gqlforge` **merges** the schemas into one superset used for
   validation and models. The merge only ever adds: nothing is removed
   from any source.
3. Each operation is **pruned** per source: a field a source cannot
   serve is dropped from *that source's* query text only. A field no
   source serves is a typo and fails the build.
4. It emits pydantic models (one per schema type, every field
   defaulting to `UNSET`), the per-source query texts, and sync + async
   client classes derived from one spec, so they cannot drift.

Concretely: if `Widget.newThing` exists only in development, the
development query selects it, the production query silently doesn't,
and on a production client `widget.new_thing` is `UNSET` - distinct
from a server-returned `None`. Development never loses a field because
production lags.

## Commands

Run from the consuming project's root; full options in {doc}`cli`.

| Command | What it does |
| --- | --- |
| `gqlforge generate` | Merge, validate, prune, emit |
| `gqlforge check` | Generate + fail on any diff vs committed output (CI) |
| `gqlforge readiness` | What the newest source has that the oldest lacks |
| `gqlforge download [source]` | Refresh committed SDL via introspection |
| `gqlforge scaffold <domain>` | Skeleton for a new domain |

## Where to start

In order: {doc}`configuration` (the `[tool.gqlforge]` table and the
small runtime contract your package provides), then {doc}`domains` (how
folders become client attributes - or how to skip domains entirely).
{doc}`docstrings` and {doc}`pipeline` are for authors and maintainers.

`gqlforge` is developed in the
[`gpp-client2` monorepo](https://github.com/gemini-hlsw/gpp-client2);
that client is its reference consumer.

```{toctree}
:hidden:
:maxdepth: 1

configuration
domains
docstrings
pipeline
cli
changelog
```
