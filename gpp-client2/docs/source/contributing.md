# Contributing

The project's `README.md` and `CLAUDE.md` (plus the monorepo root's
`CLAUDE.md` for repo-wide conventions) are the authoritative
development guides. This page is the short version: how the pieces fit,
and the rules that keep them fitting.

## Setup and checks

The client is one member of a uv workspace monorepo; sync once at the
repository root, then work from `gpp-client2/`:

```bash
uv sync --all-packages       # at the repository root, once
cd gpp-client2
uv run pytest                              # offline suite, no network
uv run mypy                                # strict typing
uv run sphinx-build -W docs/source docs/_build   # this documentation
cd .. && uv run ruff check .               # lint (whole workspace)
```

## How the package is produced

One operations tree, `graphql/operations/<domain>/*.graphql`, holds the
union of every GraphQL selection the client can make. The `gqlforge` codegen
library (developed in the `gqlforge/` directory of this repository,
configured by `[tool.gqlforge]` in pyproject.toml) merges the committed
per-environment
schemas, prunes each operation for each environment, and emits the
generated layer: pydantic models, input types, the per-environment
operation map, and the sync and async domain base classes.

```bash
uv run gqlforge generate    # after editing operations or emitters
uv run gqlforge check       # CI fails if committed output is stale
uv run gqlforge readiness   # cross-environment promotion report
```

Nothing under `src/gpp_client2/_generated/` is edited by hand.

## Adding an operation

Write the operation in the right domain directory, name it
`<verb><Resource>[By<Key>]` so its method name derives, and run `gqlforge`.
The result is a typed method on both clients and a CLI command, with no
further wiring.

Document an operation by writing a `#` comment block directly above it
in the `.graphql` file - it becomes the generated method's docstring,
verbatim (the `watch*` subscriptions are examples). Everything else about
the pipeline - the folder-to-domain mapping, no-domain and models-only
layouts, the `[tool.gqlforge]` reference, and the stage-by-stage
internals - lives in the
[`gqlforge` documentation](https://gqlforge.readthedocs.io),
with `graphql/operations/README.md` as the in-tree quick reference.

## Changing what an existing query selects

Every method's selection - including the wide GOATS and scheduler
queries - is a plain GraphQL file. To add or remove fields, edit the
operation (for example `graphql/operations/goats/queries.graphql`; shared
fragments live in `graphql/operations/_shared/`), run
`uv run gqlforge generate`, and commit the source together with
the regenerated output.

Environment differences are handled for you. Codegen validates the edited
selection against every committed environment schema:

- A field only development serves is kept in development's query text and
  pruned from the environments that cannot serve it, where the model
  attribute stays `UNSET` at runtime.
- A field no environment serves fails the build, so a typo cannot ship.
- The `graphql/availability.json` diff shows which environments serve
  each field, and `uv run gqlforge readiness` reports when the
  others catch up.

## The conformance rule

Coverage gaps fail tests, not reviews. The conformance suite checks that
every operation is reachable as a domain method, that sync and async
surfaces are identical, that the CLI exposes every method, and that the
bundled agent skill documents every public method. If you extend the API,
the tests tell you every place that has to keep up.

## Changelog and commit messages

Commit messages follow
[Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): summary`, with `type` one of `feat`, `fix`, `perf`,
`docs`, `removal`, `misc`, `test`, `refactor`, `chore`, or `ci`. They
are not just style:
[release-please](https://github.com/googleapis/release-please) compiles
each package's `CHANGELOG.md` and next version straight from the
commits that touch it, so any change a user of the library would notice
must carry a `feat`/`fix`/`perf`/`removal` subject line written for
those users (breaking changes say `feat!:` or add a
`BREAKING CHANGE:` footer). `CHANGELOG.md` is never edited by hand.

Releasing is merging the release PR that release-please keeps open for
the package; the same workflow then publishes to PyPI.

## Live tests

The offline suite is the default and runs everywhere. Tests marked `live`
talk to a real deployment and need a token; write tests additionally
require `GPP_LIVE_WRITE=1` and follow strict creation budgets and
ledger-tracked cleanup. See the README for the full rules.
