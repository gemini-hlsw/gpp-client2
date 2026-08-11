# Contributing

The repository's `README.md` and `CLAUDE.md` are the authoritative
development guides. This page is the short version: how the pieces fit,
and the rules that keep them fitting.

## Setup and checks

```bash
uv sync
uv run pytest                              # offline suite, no network
uv run ruff check . && uv run mypy         # lint and strict typing
uv run sphinx-build -W docs/source docs/_build   # this documentation
```

## How the package is produced

One operations tree, `graphql/operations/<domain>/*.graphql`, holds the
union of every GraphQL selection the client can make. A custom codegen
package (`codegen/`, not shipped) merges the committed per-environment
schemas, prunes each operation for each environment, and emits the
generated layer: pydantic models, input types, the per-environment
operation map, and the sync and async domain base classes.

```bash
uv run python -m codegen generate    # after editing operations or emitters
uv run python -m codegen check       # CI fails if committed output is stale
uv run python -m codegen readiness   # cross-environment promotion report
```

Nothing under `src/gpp_client2/_generated/` is edited by hand.

## Adding an operation

Write the operation in the right domain directory, name it
`<verb><Resource>[By<Key>]` so its method name derives, and run codegen.
The result is a typed method on both clients and a CLI command, with no
further wiring.

## The conformance rule

Coverage gaps fail tests, not reviews. The conformance suite checks that
every operation is reachable as a domain method, that sync and async
surfaces are identical, that the CLI exposes every method, and that the
bundled agent skill documents every public method. If you extend the API,
the tests tell you every place that has to keep up.

## Live tests

The offline suite is the default and runs everywhere. Tests marked `live`
talk to a real deployment and need a token; write tests additionally
require `GPP_LIVE_WRITE=1` and follow strict creation budgets and
ledger-tracked cleanup. See the README for the full rules.
