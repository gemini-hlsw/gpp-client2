# The codegen pipeline

This package is a development tool - it is not shipped in the wheel. It
turns two inputs, the committed environment schemas in `graphql/schemas/`
and the single union operations tree in `graphql/operations/`, into
everything under `src/gpp_client2/_generated/`. Run it with
`uv run python -m codegen <subcommand>` (`generate`, `check`, `readiness`,
`download`, `scaffold`).

The design premise: GPP's environments genuinely diverge in both
directions, and nothing in the operations tree marks a field as
environment-specific. All environment awareness is *derived* here, at
build time, and committed as reviewable artifacts.

The heavy lifting is delegated to
[graphql-core](https://graphql-core-3.readthedocs.io/): parsing,
validation, schema building, AST printing. This package contributes only
what no library ships - the multi-environment logic - as walks over
graphql-core AST nodes.

## Stages, in pipeline order

### 1. Schema loading and merging - `schema.py`

Builds each environment's schema from its committed SDL, then a **merged
schema**: union of types, union of fields per type, union of enum values.
Nullability differences relax to the nullable form. Structural
divergences (same field, incompatible types across environments) are
recorded, not fatal - they become errors only if an operation actually
selects the divergent field. `download` refreshes the committed SDL via
an introspection request (needs a token).

### 2. Operations tree loading - `operations.py`

Loads `graphql/operations/<domain>/*.graphql`, where the directory names
the domain and `_`-prefixed directories hold shared fragments. Every
operation is validated against the *merged* schema first - a selection
that exists nowhere is a typo and fails the build here. `__typename` is
injected into interface- and union-typed selections so responses can be
parsed into discriminated unions.

### 3. Per-environment pruning - `prune.py`

The heart of the pipeline. Each operation is pruned against each
environment schema: a selection the schema cannot serve is dropped, empty
selection sets prune their parent recursively, fragments die at a
fixpoint, and unused variables are removed. Every pruned document is
re-validated against its environment schema - the pruner never emits
query text the server would reject. What survives where is recorded and
becomes `graphql/availability.json`, the committed manifest whose diff in
a schema-sync PR *is* the promotion ceremony. Two invariants to preserve
when editing: a selection surviving in no environment is a build error,
and `__typename`-only selection sets are never pruned (authors probe
types that way).

### 4. Model emission - `emit_models.py`

From the merged schema: `scalars.py` (type aliases), `enums.py`
(`StrEnum`s), `inputs.py` (pydantic models whose `graphql_dump` uses
`exclude_unset` for omit-vs-null semantics), and `models.py` (one pydantic
model per object/interface type, plus discriminated-union aliases for
abstract types). Every output field defaults to the `UNSET` sentinel, so
"the operation did not select this" and "this environment cannot serve
this" are both distinct from a server-returned `None`. Aliases use
`validation_alias`/`serialization_alias`, never `alias=` (see CLAUDE.md
for why).

### 5. Operation emission - `emit_operations.py`

For every operation: a method name derived from the
`<verb><Resource>[By<Key>]` naming convention (`naming.py`), a signature
from the operation's variable definitions, and a return type found by
unwrapping single-field selection chains at the root (so
`createProgram { program { ... } }` returns a `Program`, not a wrapper).
Emits the per-environment operation map and the sync and async domain
base classes from the same spec, which is what keeps the two surfaces
identical by construction.

### 6. Orchestration - `pipeline.py`, `scaffold.py`

`generate` runs stages 1-5 and writes the merged schema, availability
manifest, and generated modules. `check` regenerates into a temp dir and
fails if the committed artifacts differ (CI runs this). `readiness`
prints the cross-environment promotion report. `scaffold <domain>`
creates a new domain's operations directory and hand-written module, then
prints the wiring steps the conformance tests enforce.

## Safety nets

Correctness is enforced at three layers, so edits here fail fast rather
than at runtime: generation-time validation (merged-schema validation of
every operation, re-validation of every pruned document), `codegen check`
in CI (committed artifacts can never be stale), and the offline test
suite (`tests/test_merge.py`, `tests/test_prune.py`,
`tests/test_naming.py`, and `tests/test_inject_typename.py` unit-test
this package; `tests/test_conformance.py` pins the generated surface).
