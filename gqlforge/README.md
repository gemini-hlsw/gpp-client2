# gqlforge

Multi-schema GraphQL-to-Python code generation: one union operations
tree, validated against the merge of every schema you serve, pruned per
schema, and emitted as pydantic models plus sync and async client bases.

**Documentation:**
[gqlforge.readthedocs.io](https://gqlforge.readthedocs.io)

Most GraphQL codegen tools assume one schema. `gqlforge` exists for the case
they don't cover: the same API deployed in several environments that
genuinely diverge - development ahead on new fields *and* on removals -
where you want **one** client package whose environment is a runtime
choice, not an install-time one. It grew inside
[`gpp-client2`](https://github.com/gemini-hlsw/gpp-client2), the client
for the Gemini Program Platform, and is developed in that repository.

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

## Configuration

`gqlforge` is driven by a `[tool.gqlforge]` table in the consuming project's
pyproject.toml; run `gqlforge <command>` from the project root:

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
domains_dir = "src/myclient/domains"     # for `gqlforge scaffold` (optional)
environments = "myclient.environments:ENVIRONMENTS"      # download hook
download_token = "myclient.config:find_download_token"   # optional
token_env = "MY_TOKEN"                   # download token fallback
```

By default `gqlforge` vendors a complete runtime into the generated
package - `UNSET` machinery, sync+async httpx executors, a
graphql-transport-ws subscription transport, and a ready-made
`Client`/`AsyncClient` - so a schema plus queries yields a working
client with zero hand-written code, and generated output never depends
on `gqlforge` at runtime. Set `runtime_package` to bring your own
runtime instead (the contract: `._base` provides the bases and `UNSET`,
`._executor` the executors); `gpp-client2` is the reference
implementation of that path.

## Domains: from folder to client attribute

You never pass a domain list anywhere - **creating a directory declares
a domain**, and everything downstream is derived:

1. **Declare.** Make `operations/<domain>/` (a snake_case identifier)
   and put `.graphql` files in it. The directory name is the domain key.
   `_`-prefixed directories (`_shared/`) hold fragments and never become
   domains.
2. **`gqlforge` maps.** Every operation in the directory is tagged with that
   domain. The folder name is pascal-cased and two classes are emitted
   into `<generated_package>.domains`:

   ```
   operations/program/          class ProgramOperations:
     queries.graphql       ->       def __init__(self, executor: SyncExecutor)
     mutations.graphql          class AsyncProgramOperations:
                                    def __init__(self, executor: AsyncExecutor)
   ```

   Each operation becomes one method on both classes, its name derived
   from the operation name (`getProgramById` -> `get_by_id`,
   `createProgram` -> `create`). The classes need nothing but an
   executor - how you expose them is up to you.
3. **You structure.** The recommended pattern (gpp-client2's, enforced
   there by a conformance test) is one subclass per domain plus one
   registry:

   ```python
   # domains/program.py - inherit full coverage, add curated helpers
   class ProgramAPI(ProgramOperations):
       def get_all_active(self):  # curated logic lives here
           ...


   # domains/__init__.py - folder key -> (attribute, sync, async)
   DOMAIN_REGISTRY = {
       "program": ("programs", ProgramAPI, AsyncProgramAPI),
   }

   # client constructor
   for attribute, sync_cls, _ in DOMAIN_REGISTRY.values():
       setattr(self, attribute, sync_cls(executor))
   ```

   The registry is the one place a human names things: the folder
   `program` becomes the attribute `client.programs`. It also pays for
   itself downstream - `gpp-client2` derives its entire CLI and its
   per-domain reference docs by reflecting over the same registry.

`gqlforge scaffold <domain>` automates step 3: it creates the operations
directory and the subclass module, then prints the remaining wiring.

### Don't want domains?

Both structures are optional:

- **No domains**: put `.graphql` files directly at the operations-tree
  root. They form one anonymous domain emitted as plain `Operations` /
  `AsyncOperations` classes, and with no domain to strip, method names
  keep their resource (`getWidgetById` -> `get_widget_by_id`). Your
  whole client can be `Operations(executor)`.
- **No operations at all**: with no operations tree, `gqlforge` is a
  models-only generator - it emits the pydantic scalars, enums, inputs,
  and models from the merged schema and skips the operation pipeline.
- **One schema**: a single entry in `source_order` makes the merge and
  pruning no-ops; you get an ordinary single-schema codegen with the
  multi-schema machinery dormant until you commit a second SDL.

## Docstrings

Documentation flows from two sources, by precedence:

1. **A leading `#` comment block** directly above an operation becomes
   that method's docstring opening, verbatim and multi-line:

   ```graphql
   # Fetch a widget by its identifier.
   # Returns UNSET fields for anything not selected.
   query getWidgetById($id: ID!) { widget(id: $id) { id name } }
   ```

   A blank line breaks the attachment, so file-header comments separated
   by one blank line are never mistaken for documentation. (GraphQL
   forbids `"""` descriptions on executable operations, which is why
   the comment convention exists.)
2. **Schema SDL descriptions** flow automatically everywhere else: type
   and field descriptions become model docstrings, and an operation
   with no comment block uses the schema's root-field description as
   its summary.

Parameter, return, and yield sections are always derived from the
operation's variables and return shape - authors write the *why*, `gqlforge`
writes the *signature*.

## Commands

| Command | What it does |
| --- | --- |
| `gqlforge generate` | Merge, validate, prune, and emit everything |
| `gqlforge check` | Run generate; fail if committed artifacts changed (CI) |
| `gqlforge readiness` | Cross-schema promotion report |
| `gqlforge download [source]` | Refresh schema SDL via introspection |
| `gqlforge scaffold <domain>` | Skeleton for a new domain |

## Stages, in pipeline order

The heavy lifting is delegated to
[graphql-core](https://graphql-core-3.readthedocs.io/): parsing,
validation, schema building, AST printing. `gqlforge` contributes the
multi-schema logic as walks over graphql-core AST nodes.

### 1. Schema loading and merging - `schema.py`

Builds each source's schema from its SDL, then a **merged schema**:
union of types, union of fields per type, union of enum values.
Nullability differences relax to the nullable form. Structural
divergences (same field, incompatible types across sources) are
recorded, not fatal - they become errors only if an operation actually
selects the divergent field. `download` refreshes SDL via an
introspection request.

### 2. Operations tree loading - `operations.py`

Loads `<operations>/<domain>/*.graphql`, where the directory names the
domain and `_`-prefixed directories hold shared fragments. Every
operation is validated against the *merged* schema first - a selection
that exists nowhere fails the build here. `__typename` is injected into
interface- and union-typed selections so responses can be parsed into
discriminated unions.

### 3. Per-schema pruning - `prune.py`

The heart of the pipeline. Each operation is pruned against each schema:
a selection the schema cannot serve is dropped, empty selection sets
prune their parent recursively, fragments die at a fixpoint, and unused
variables are removed. Every pruned document is re-validated against its
schema - the pruner never emits query text a server would reject. What
survives where becomes the availability manifest. Two invariants to
preserve when editing: a selection surviving in no schema is a build
error, and `__typename`-only selection sets are never pruned (authors
probe types that way).

### 4. Model emission - `emit_models.py`

From the merged schema: scalars (type aliases), enums (`StrEnum`s),
inputs (pydantic models whose serialization uses `exclude_unset` for
omit-vs-null semantics), and one output model per object/interface type
plus discriminated-union aliases for abstract types. Every output field
defaults to the `UNSET` sentinel. Aliases use
`validation_alias`/`serialization_alias`, never `alias=` (mypy's
dataclass_transform would make the alias the constructor parameter name).

### 5. Operation emission - `emit_operations.py`

For every operation: a method name derived from the
`<verb><Resource>[By<Key>]` naming convention (`naming.py`), a signature
from the operation's variable definitions, and a return type found by
unwrapping single-field selection chains at the root (so
`createProgram { program { ... } }` returns a `Program`, not a wrapper).
Emits the per-source operation map and the sync and async domain base
classes from the same spec - which is what keeps the two surfaces
identical by construction.

### 6. Orchestration - `pipeline.py`, `scaffold.py`

`generate` runs stages 1-5. `check` regenerates and fails if committed
artifacts differ (run it in CI). `readiness` prints the cross-schema
promotion report. `scaffold <domain>` creates a new domain's operations
directory and hand-written module, then prints the wiring steps.

## Safety nets

Correctness is enforced at three layers, so edits fail fast rather than
at runtime: generation-time validation (merged-schema validation of
every operation, re-validation of every pruned document), `gqlforge check`
in CI (committed artifacts can never be stale), and the test suite: unit tests in
`tests/` covering the merge, prune, naming, and `__typename` injection
logic.
