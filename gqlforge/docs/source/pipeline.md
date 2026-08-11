# The pipeline

The heavy lifting is delegated to
[graphql-core](https://graphql-core-3.readthedocs.io/): parsing,
validation, schema building, AST printing. gqlforge contributes the
multi-schema logic as walks over graphql-core AST nodes.

## Stages, in order

### 1. Schema loading and merging - `schema.py`

Builds each source's schema from its SDL, then a **merged schema**: the
union of types, of fields per type, and of enum values. The merge is
strictly additive - it never removes anything from any source. A field
that exists only in development is fully available to development;
omission happens later, in pruning (stage 3), and only for the sources
that cannot serve the field. Nullability differences relax to the
nullable form, and structural divergences (same field, incompatible
types across sources) are recorded, becoming errors only if an
operation selects them. `download` refreshes SDL via introspection.

### 2. Operations tree loading - `operations.py`

Loads `<operations>/<domain>/*.graphql`, where the directory names the
domain and `_`-prefixed directories hold shared fragments. Every
operation is validated against the *merged* schema first - a selection
that exists nowhere fails the build here. `__typename` is injected into
interface- and union-typed selections so responses can be parsed into
discriminated unions, and each operation's leading comment block is
captured for its docstring.

### 3. Per-schema pruning - `prune.py`

The heart of the pipeline. Each operation is pruned against each
schema: a selection the schema cannot serve is dropped, empty selection
sets prune their parent recursively, fragments die at a fixpoint, and
unused variables are removed. Every pruned document is re-validated
against its schema - the pruner never emits query text a server would
reject. What survives where becomes the availability manifest. Two
invariants to preserve when editing: a selection surviving in no schema
is a build error, and `__typename`-only selection sets are never pruned
(authors probe types that way).

### 4. Model emission - `emit_models.py`

From the merged schema: scalars (type aliases), enums (`StrEnum`s),
inputs (pydantic models whose serialization uses `exclude_unset` for
omit-vs-null semantics), and one output model per object/interface type
plus discriminated-union aliases for abstract types. Every output field
defaults to the `UNSET` sentinel. Aliases use
`validation_alias`/`serialization_alias`, never `alias=` (mypy's
dataclass_transform would make the alias the constructor parameter
name).

### 5. Operation emission - `emit_operations.py`

For every operation: a method name derived from the
`<verb><Resource>[By<Key>]` naming convention (`naming.py`), a
signature from the operation's variable definitions, and a return type
found by unwrapping single-field selection chains at the root (so
`createProgram { program { ... } }` returns a `Program`, not a
wrapper). Emits the per-source operation map and the sync and async
domain base classes from the same spec - which is what keeps the two
surfaces identical by construction.

### 6. Orchestration - `pipeline.py`, `scaffold.py`

`generate` runs stages 1-5. `check` regenerates and fails if committed
artifacts differ (run it in CI). `readiness` prints the cross-schema
promotion report. `scaffold <domain>` creates a new domain's operations
directory and hand-written module, then prints the wiring steps.

## Safety nets

Correctness is enforced at three layers, so edits fail fast rather than
at runtime: generation-time validation (merged-schema validation of
every operation, re-validation of every pruned document), `gqlforge
check` in CI (committed artifacts can never be stale), and the unit
tests covering the merge, prune, naming, and `__typename` injection
logic, an end-to-end test that generates a complete minimal consumer,
and a corpus suite that generates from snapshots of real public
GraphQL schemas (Countries, Rick and Morty, SWAPI, AniList, and
GitHub's full 1.5 MB schema) and then *imports and instantiates* the
emitted models - so real-world schema shapes, not just fixtures we
invented, gate every change.

## Where the code lives

gqlforge is developed in the
[gpp-client2 repository](https://github.com/gemini-hlsw/gpp-client2)
under `gqlforge/`, as a uv workspace member, with gpp-client2 itself as
the reference consumer exercising every feature in production.
