# gpp-client2

Python client for the Gemini Program Platform (GPP). One package, any
deployment (development/staging/production) as a runtime choice, dual
sync/async API, everything derived from one operations tree by a custom
codegen pipeline.

## Commands

```bash
uv sync                                  # install
uv run pytest                            # offline suite (fast, no network)
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python -m codegen generate        # regenerate after editing graphql/operations/
uv run python -m codegen check           # fail if committed artifacts are stale
uv run python -m codegen readiness       # promotion report across environments
uv run python -m codegen download [env]  # refresh schemas (needs a token)
uv run python -m codegen scaffold <name> # skeleton for a new domain
uv run pytest -m live                    # read-only tests against a real deployment
GPP_LIVE_WRITE=1 uv run pytest -m live   # + write round-trips (see rules below)
uv run gpp2 --help                        # the CLI (every domain method is a command)
uv run sphinx-build -W docs/source docs/_build  # build the documentation
```

## Architecture in one breath

`graphql/operations/<domain>/*.graphql` is the single union operations tree
(the product). `codegen/` (dev-only, not shipped) merges the committed
environment schemas in `graphql/schemas/`, prunes each operation per
environment, and emits everything under `src/gpp_client2/_generated/`: pydantic
models (one per schema type, every field defaulting to `UNSET`), inputs
(omit-vs-null via `exclude_unset`), the per-environment operation map plus
`graphql/availability.json`, and sync+async domain base classes. Hand-written
subclasses in `src/gpp_client2/domains/` add curated logic (workflow-state
transition guards, scheduler tree assembly, attachment REST transfer) and are
wired to `GPPClient`/`AsyncGPPClient` via `DOMAIN_REGISTRY`. Queries and
mutations run over httpx; subscriptions (`watch_*`, one graphql-transport-ws
connection per call, `src/gpp_client2/_ws.py`) run over `websockets`, whose
sync and asyncio clients keep the two surfaces identical. The `gpp2` CLI
(`src/gpp_client2/cli.py`) derives every command from the sync domain APIs by
reflection at startup - no generated file, cannot drift, and
`tests/test_cli.py` pins the rule.

## Hard rules

- NEVER edit `src/gpp_client2/_generated/` or `graphql/schemas/merged.graphql`
  or `graphql/availability.json` by hand; edit operations/emitters and run
  `codegen generate`.
- Every operation must be reachable as a domain method with identical sync
  and async surfaces; `tests/test_conformance.py` enforces this, so a
  coverage gap is a test failure, not a review comment.
- Operation names follow `<verb><Resource>[By<Key>]` so method names derive
  (see `codegen/naming.py`); rename operations rather than special-casing.
- Every user-visible change (new feature, fix, removal, behavior change -
  anything a library user would notice) ships with a towncrier fragment in
  `changelog.d/` in the same commit: `<issue>.<type>.md` or
  `+<slug>.<type>.md`, types `feat|fix|perf|docs|removal|misc` (see
  `changelog.d/README.md`). NEVER edit `CHANGELOG.md` by hand; it is
  compiled by `towncrier build` at release.
- Commit messages follow Conventional Commits: `type(scope): summary`,
  same types as the fragments plus `test|refactor|chore|ci`.
- The public-API skill (`.claude/skills/gpp-client2/SKILL.md`) documents every
  client attribute and public method; `tests/test_skill_doc.py` fails when
  the API changes without the skill being updated. Update the skill in the
  same change that changes the API.
- Aliases in generated models use `validation_alias`/`serialization_alias`,
  never `alias=` (mypy's dataclass_transform would make the alias the
  constructor parameter name and break user code).
- GraphQL partial responses: raise only when every root field is null;
  otherwise return data and log a warning (fresh observations legitimately
  error on background-calculated fields). The same rule applies per
  subscription event.
- Do not prune `__typename`-only selection sets; authors probe types that
  way (GOATS `opportunity { __typename }`).

## Live testing rules (authorized by Dan, 2026-08-10)

- Write tests create at most 2 items per domain, 50 total, with neutral
  nonce-suffixed names (`Test program <8hex>`), record every created ID in
  `.live-test-ledger.json` before anything else, and delete ONLY recorded
  IDs - never name matches. Crashed-run leftovers are healed at next start.
- Double opt-in: `-m live` AND `GPP_LIVE_WRITE=1`.
- Config: `~/.config/gpp-client2/config.toml` (profiles); tests isolate via
  `GPP_CONFIG_FILE`. Currently only a production token exists (Dan's dev
  token is corrupted); all live testing so far ran against production.

## Roadmap / next steps

1. **Set up the GitHub remote** and secrets (`GPP_LIVE_TOKEN` for
   live_tests.yaml, a PR-capable token for schema_sync.yaml).
2. **Verify prod-only field VALUES** (Igrins2/F2 offsets, saveSVCImages) -
   needs a token that can see F2/IGRINS2 observations; Dan's sees only his
   test program. Query text is already validated by production.
3. **Dev-token tasks once Dan has a replacement**: run the write round-trips
   against development, re-download the dev schema (committed copy predates
   known drift: ToO trigger types, TooActivation rename).
4. **site_status domain** (scrapes a status web page in the old client) -
   port if still wanted.
5. **Token hygiene**: Dan's prod token passed through a chat transcript;
   rotate it.
6. **Release**: the distribution is `gpp-client2` (Dan's decision,
   2026-08-10); tag `vX.Y.Z` for uv-dynamic-versioning before any release.
7. **ReadTheDocs**: connect the repo on readthedocs.org once the GitHub
   remote exists; `.readthedocs.yaml` and the Sphinx tree are committed.
