# gqlforge

gqlforge is a multi-schema GraphQL-to-Python code generator: one union
operations tree, validated against the merge of every schema you serve,
pruned per schema, and emitted as pydantic models plus sync and async
client bases that cannot drift apart.

Most GraphQL codegen tools assume one schema. gqlforge exists for the
case they don't cover: the same API deployed in several environments
that genuinely diverge - development ahead on new fields *and* on
removals - where you want **one** client package whose environment is a
runtime choice, not an install-time one. It grew inside
[gpp-client2](https://gpp-client2.readthedocs.io), the client for the
Gemini Program Platform, which remains its reference consumer.

## The model

- **One operations tree.** `operations/<domain>/*.graphql` holds the
  union of every selection used anywhere. Nothing marks a field as
  environment-specific by hand.
- **Merged-schema validation.** Every operation must validate against
  the union of all schemas - a selection no schema serves is a typo and
  fails the build.
- **Per-schema pruning.** Each operation is pruned against each schema:
  a selection a schema cannot serve is dropped from that schema's query
  text only, and every pruned document is re-validated. What survives
  where is committed as an availability manifest whose diff is your
  promotion review.
- **One set of models,** generated from the merged schema, every field
  defaulting to an `UNSET` sentinel - so "not selected", "not available
  here", and "server returned null" are three distinguishable things.
- **Sync and async surfaces from one spec,** so they cannot drift.

## Commands

Run from the consuming project's root (the directory holding the
pyproject.toml with a `[tool.gqlforge]` table):

| Command | What it does |
| --- | --- |
| `gqlforge generate` | Merge, validate, prune, and emit everything |
| `gqlforge check` | Run generate; fail if committed artifacts changed (CI) |
| `gqlforge readiness` | Cross-schema promotion report |
| `gqlforge download [source]` | Refresh schema SDL via introspection |
| `gqlforge scaffold <domain>` | Skeleton for a new domain |

## Where to start

{doc}`configuration` covers the `[tool.gqlforge]` table and the runtime
contract your package provides. {doc}`domains` explains how folders
become client attributes - and the layouts for projects that don't want
domains at all. {doc}`docstrings` shows how documentation flows from
your GraphQL sources into the generated methods, and {doc}`pipeline`
walks the generator stage by stage.

```{toctree}
:hidden:
:maxdepth: 1

configuration
domains
docstrings
pipeline
changelog
```
