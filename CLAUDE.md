# gpp-client2 monorepo

Two uv workspace members sharing one lock, venv, and CI:

- **`gpp-client2/`** - Python client for the Gemini Program Platform:
  one package, any deployment as a runtime choice, dual sync/async API,
  `gpp2` CLI. Specifics: `gpp-client2/CLAUDE.md`.
- **`gqlforge/`** - the multi-schema GraphQL-to-Python codegen that
  produces the client's generated layer; gpp-client2 is its reference
  consumer. Specifics: `gqlforge/CLAUDE.md`.

The repo root is a virtual workspace: sync once at the root, then run
project commands from inside the member directories.

```bash
uv sync --all-packages                    # install (repo root, once)
uv run ruff check . && uv run ruff format --check .   # lint (repo root)
cd gpp-client2 && uv run pytest           # client suite (see its CLAUDE.md)
cd gqlforge && uv run pytest              # codegen suite (see its CLAUDE.md)
```

## Repo-wide rules

- Every user-visible change (new feature, fix, removal, behavior change -
  anything a library user would notice) ships with a towncrier fragment in
  the same commit, in the changelog.d/ of the project it changes
  (`gpp-client2/changelog.d/` or `gqlforge/changelog.d/`):
  `<issue>.<type>.md` or `+<slug>.<type>.md`, types
  `feat|fix|perf|docs|removal|misc` (see either changelog.d/README.md).
  NEVER edit a CHANGELOG.md by hand; both are compiled by
  `towncrier build` at release.
- Commit messages follow Conventional Commits: `type(scope): summary`,
  same types as the fragments plus `test|refactor|chore|ci`.
- Agent skills live at `.claude/skills/`: `gpp-client2` (using the
  client library) and `gqlforge` (using the codegen). Each is pinned by
  a skill-doc test in its project; update the skill in the same change
  that changes the surface it documents.
- A change to gqlforge is not done until the reference consumer agrees:
  run gpp-client2's `uv run gqlforge check` and test suite after any
  emitter or pipeline change.

## Repo-level roadmap

1. **CI secrets** (remote exists; secrets do not yet): `GPP_DEV_TOKEN`
   and `GPP_PROD_TOKEN` (shared by live_tests.yaml and
   schema_sync.yaml), `SCHEMA_SYNC_TOKEN` (PR-capable, for
   schema_sync.yaml), and the `LIVE_TESTS_ENABLED=true` repo variable to
   arm the nightly live runs.
2. **ReadTheDocs**: create the `gpp-client2` project with "Build
   configuration file" `gpp-client2/.readthedocs.yaml`, then a
   `gqlforge` project on the same repo with it set to
   `gqlforge/.readthedocs.yaml`, and add the latter as a subproject of
   gpp-client2 (Admin -> Subprojects, alias `gqlforge`). Both Sphinx
   trees and RTD configs are committed.
3. **Eventual gqlforge split**: when it leaves the monorepo, flip
   `[tool.uv.sources]` in gpp-client2 from `workspace = true` to a
   version pin and repoint the gqlforge RTD project's Git URL.
