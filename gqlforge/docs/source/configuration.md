# Configuration

`gqlforge` is driven entirely by a `[tool.gqlforge]` table in the
consuming project's pyproject.toml. All paths resolve relative to the
pyproject's directory, so `gqlforge <command>` works from the project
root with no arguments.

```toml
[tool.gqlforge]
schemas = "graphql/schemas"              # <source>.graphql SDL files
operations = "graphql/operations"        # the union operations tree
output = "src/myclient/_generated"
merged_schema = "graphql/schemas/merged.graphql"
availability = "graphql/availability.json"
source_order = ["development", "staging", "production"]  # newest first
generated_package = "myclient._generated"
runtime_package = "myclient"             # exposes ._base and ._executor
model_base = "Model"                     # class in <runtime>._base
input_base = "Input"
domains_dir = "src/myclient/domains"     # for `gqlforge scaffold`
environments = "myclient.environments:ENVIRONMENTS"      # download hook
download_token = "myclient.config:find_download_token"   # optional
token_env = "MY_TOKEN"                   # download token fallback
```

## Key reference

| Key | Required | Meaning |
| --- | --- | --- |
| `schemas` | yes | Directory holding one `<source>.graphql` SDL file per schema source |
| `operations` | yes | The union operations tree; may be empty or absent for models-only use |
| `output` | yes | Directory the generated modules are written to |
| `merged_schema` | yes | Where the merged (union) schema SDL is written |
| `availability` | yes | Where the availability manifest JSON is written |
| `source_order` | yes | Schema sources, newest first; a source participates only when its SDL file exists |
| `generated_package` | yes | Dotted import path of the generated package, used in emitted cross-module imports |
| `runtime_package` | yes | Package exposing the runtime contract (see below) |
| `model_base` | no (`Model`) | Class in `<runtime_package>._base` that output models inherit |
| `input_base` | no (`Input`) | Class in `<runtime_package>._base` that input models inherit |
| `domains_dir` | no | Where `gqlforge scaffold` writes hand-written domain modules |
| `environments` | no | `module:attribute` import string for the download registry - an iterable of objects with `name` and `base_url` attributes |
| `download_token` | no | `module:attribute` import string for a callable `(source_name) -> str \| None` supplying a download token |
| `token_env` | no | Environment variable consulted for a download token when the hook is absent or returns `None` |

## The runtime contract

Generated code imports a small contract from your package rather than
from `gqlforge`, which keeps `gqlforge` a development-only dependency:

- `<runtime_package>._base` must provide the `UNSET` sentinel, an
  `UnsetType`, and the two base classes named by `model_base` and
  `input_base`. Output models inherit the model base and default every
  field to `UNSET`; input models inherit the input base, whose
  serialization uses pydantic's `exclude_unset` so an omitted field and
  an explicit `null` stay distinct on the wire.
- `<runtime_package>._executor` must provide `SyncExecutor` and
  `AsyncExecutor` - the objects the emitted domain bases call to run an
  operation. Each domain class constructor takes exactly one executor.

`gpp-client2`'s
[`_base.py` and `_executor.py`](https://github.com/gemini-hlsw/gpp-client2/tree/main/gpp-client2/src/gpp_client2)
are the reference implementation of both halves.

## What you name, what gqlforge names

`gqlforge` never names your client. There is no generated client class -
you write the top-level client yourself, call it anything
(`GPPClient`, `MyClient`), and wrap the generated pieces in it. The
full division:

| You choose | Via |
| --- | --- |
| Package, client class, and attribute names (`client.programs`) | Ordinary Python code and your registry |
| Where generated code lives and its import path | `output`, `generated_package` |
| The base classes generated models inherit | `model_base`, `input_base` |

| `gqlforge` derives | From |
| --- | --- |
| Domain class names (`ProgramOperations`, `AsyncProgramOperations`) | Operations folder names |
| Method names (`get_by_id`) | Operation names |
| Model, enum, and input class names | Schema type names |

## Schema downloads

`gqlforge download [source]` refreshes a committed SDL file via a
GraphQL introspection request. The endpoint comes from the
`environments` import hook, and the bearer token from the
`download_token` hook if configured, else the `token_env` environment
variable. A source whose registry entry has `base_url = None` is
skipped - useful for environments that are declared but not deployed
yet.
