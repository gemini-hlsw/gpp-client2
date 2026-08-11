---
name: gqlforge
description: Configure and run gqlforge, the multi-schema GraphQL-to-Python codegen - one operations tree pruned per schema source, emitting pydantic models and sync/async client bases. Use when setting up [tool.gqlforge], writing or editing GraphQL operations for a gqlforge project, or running gqlforge generate/check/readiness/download/scaffold.
---

# Using gqlforge

`tests/test_skill_doc.py` (in gqlforge) enforces that this file names
every `[tool.gqlforge]` key and CLI subcommand - update it in the same
change as any surface change.

## Configure

Everything lives in the consuming project's pyproject.toml; run
`gqlforge <command>` from that project's root:

```toml
[tool.gqlforge]
schemas = "graphql/schemas"              # <source>.graphql SDL per source
operations = "graphql/operations"        # union operations tree
output = "src/myclient/_generated"
merged_schema = "graphql/schemas/merged.graphql"
availability = "graphql/availability.json"
source_order = ["development", "production"]   # newest first
generated_package = "myclient._generated"
runtime_package = "myclient"             # provides ._base and ._executor
model_base = "Model"                     # optional (default "Model")
input_base = "Input"                     # optional (default "Input")
domains_dir = "src/myclient/domains"     # optional, for scaffold
environments = "myclient.environments:ENVIRONMENTS"    # optional, download
download_token = "myclient.config:find_token"          # optional hook
token_env = "MY_TOKEN"                   # optional download fallback
```

The runtime contract: `<runtime_package>._base` provides `UNSET`,
`UnsetType`, and the two base classes; `<runtime_package>._executor`
provides `SyncExecutor`/`AsyncExecutor`. gpp-client2 is the reference
implementation.

## Commands

- `gqlforge generate` - merge, validate, prune, emit everything
- `gqlforge check` - generate + fail on any diff vs committed (CI)
- `gqlforge readiness` - cross-schema promotion report
- `gqlforge download [source]` - refresh SDL via introspection
- `gqlforge scaffold <domain>` - new-domain skeleton + wiring steps

## Authoring operations

- Folder = domain = one generated `<Pascal>Operations` +
  `Async<Pascal>Operations` class pair; `_`-prefixed folders hold shared
  fragments only. Files at the tree root form the anonymous domain,
  emitted as plain `Operations`/`AsyncOperations`.
- Name operations `<verb><Resource>[By<Key>]`; the resource matching the
  domain is dropped (`getProgramById` in `program/` -> `get_by_id`), its
  plural derives `_all`, a domain-prefixed resource keeps the remainder,
  and anything else is a build error - rename rather than special-case.
- A leading `#` comment block directly above an operation becomes the
  generated method's docstring, verbatim. A blank line breaks the
  attachment - keep one after file-header comments.
- Write the union of selections across all schema sources; pruning
  derives per-source query text. A selection no source serves fails the
  build.

## Gotchas

- No operations tree at all -> models-only mode (scalars, enums, inputs,
  models; no operations/domains modules).
- One entry in `source_order` -> ordinary single-schema codegen.
- `check` compares against the git index: uncommitted generated changes
  make it fail by design - commit generated output with the change.
- Emitted code imports the *consumer's* runtime package; gqlforge is
  never a runtime dependency.
- Structural divergences between sources are fatal only when an
  operation selects the divergent field; `readiness` lists them.
