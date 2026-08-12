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

- Commit messages follow Conventional Commits: `type(scope): summary`,
  types `feat|fix|perf|docs|removal|misc|test|refactor|chore|ci`. They
  are the changelog: release-please compiles each package's
  CHANGELOG.md and next version from the commits touching that package,
  so a user-visible change MUST carry a user-comprehensible
  `feat|fix|perf|removal` subject line (`feat!:` or a
  `BREAKING CHANGE:` footer for breaking changes). NEVER edit a
  CHANGELOG.md, `release-please` version line, or the release PR by
  hand.
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
2. **Release automation setup** (release-please.yaml is committed; no
   tokens involved): on PyPI, add a pending publisher for each of
   `gpp-client2` and `gqlforge` - repository `gemini-hlsw/gpp-client2`,
   workflow `release-please.yaml`, environment `pypi`. On GitHub, create
   the `pypi` environment and enable Settings -> Actions -> "Allow
   GitHub Actions to create and approve pull requests". Releasing is
   then: merge the release PR release-please keeps open per package
   (version bump + changelog from Conventional Commits; tags
   `gpp-client2-vX.Y.Z` / `gqlforge-vX.Y.Z`), and the same workflow
   publishes to PyPI.
3. **ReadTheDocs**: two independent top-level projects on the same
   repo, each with its own subdomain - `gpp-client2` with "Build
   configuration file" `gpp-client2/.readthedocs.yaml`, and `gqlforge`
   with `gqlforge/.readthedocs.yaml` (-> gqlforge.readthedocs.io). Not
   subprojects (Dan's decision, 2026-08-11): gqlforge keeps its own URL,
   which also survives the eventual repo split unchanged. Both Sphinx
   trees and RTD configs are committed.
4. **Eventual gqlforge split**: when it leaves the monorepo, flip
   `[tool.uv.sources]` in gpp-client2 from `workspace = true` to a
   version pin and repoint the gqlforge RTD project's Git URL.
