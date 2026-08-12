# gpp-client2

Python client for the Gemini Program Platform (GPP). One package, any
deployment (development/staging/production) as a runtime choice, dual
sync/async API, everything derived from one operations tree by gqlforge
(the sibling workspace member). Repo-wide rules live in the root
CLAUDE.md; run the commands below from this directory.

## Commands

```bash
uv run pytest                            # offline suite (fast, no network)
uv run mypy
uv run gqlforge generate        # regenerate after editing graphql/operations/
uv run gqlforge check           # fail if committed artifacts are stale
uv run gqlforge readiness       # promotion report across environments
uv run gqlforge download [env]  # refresh schemas (needs a token)
uv run gqlforge scaffold <name> # skeleton for a new domain
uv run pytest -m live                    # read-only tests against a real deployment
GPP_LIVE_WRITE=1 uv run pytest -m live   # + write round-trips (see rules below)
uv run gpp2 --help                        # the CLI (every domain method is a command)
uv run sphinx-build -W docs/source docs/_build  # build the documentation
```

## Architecture in one breath

`graphql/operations/<domain>/*.graphql` is the single union operations tree
(the product). gqlforge (configured by `[tool.gqlforge]` in this project's
pyproject.toml, vendored mode - no `runtime_package`) merges the committed
environment schemas in `graphql/schemas/`, prunes each operation per
environment, and emits everything under `src/gpp_client2/_generated/`:
pydantic models (one per schema type, every field defaulting to `UNSET`),
inputs (omit-vs-null via `exclude_unset`), the per-environment operation map
plus `graphql/availability.json`, sync+async domain base classes, the
vendored runtime (`_base.py`, `_executor.py`, `_ws.py`, `_exceptions.py`),
and a default client. `GPPClient`/`AsyncGPPClient` subclass that generated
client, adding config resolution, the `/odb` GraphQL and `wss://<host>/ws`
endpoint conventions, the raw-query restricted-field preflight
(`GPPExecutorCore`), and a separate root-based httpx client for REST.
Hand-written subclasses in `src/gpp_client2/domains/` add curated logic
(workflow-state transition guards, scheduler tree assembly, attachment REST
transfer) and are attached in the clients' `_wire_domains()` override;
`DOMAIN_REGISTRY` keeps registry, client, and operations tree in lockstep.
`gpp_client2/_base.py`, `_executor.py`, and `_ws.py` are one-line shims
re-exporting the vendored runtime (`GPPModel`/`GPPInput` are the vendored
`Model`/`Input`); exceptions are the vendored hierarchy re-exported from
`gpp_client2.errors` plus GPP-specific `ClientError` subclasses. Queries and
mutations run over httpx; subscriptions (`watch_*`, one graphql-transport-ws
connection per call) run over `websockets`, whose sync and asyncio clients
keep the two surfaces identical. The `gpp2` CLI (`src/gpp_client2/cli.py`)
derives every command from the sync domain APIs by reflection at startup -
no generated file, cannot drift, and `tests/test_cli.py` pins the rule.

## Hard rules

- NEVER edit `src/gpp_client2/_generated/` or `graphql/schemas/merged.graphql`
  or `graphql/availability.json` by hand; edit operations/emitters and run
  `gqlforge generate`.
- Every operation must be reachable as a domain method with identical sync
  and async surfaces; `tests/test_conformance.py` enforces this, so a
  coverage gap is a test failure, not a review comment.
- Operation names follow `<verb><Resource>[By<Key>]` so method names derive
  (see gqlforge's `naming.py`); rename operations rather than
  special-casing. A `#` comment block directly above an operation becomes
  the generated method's docstring; keep a blank line after file-header
  comments so they stay unattached.
- The public-API skill (`.claude/skills/gpp-client2/SKILL.md` at the repo
  root) documents every client attribute and public method;
  `tests/test_skill_doc.py` fails when the API changes without the skill
  being updated. Update the skill in the same change that changes the API.
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
- Config: `config.toml` in `~/.gpp-client2/` (force_posix - identical on
  every Unix; `%APPDATA%\gpp-client2\` on Windows); offline tests
  isolate via `GPP_CONFIG_FILE`, live tests use the real environment
  (`GPP_PROFILE=dev uv run pytest -m live` targets development). Working
  dev and prod tokens exist (dev added 2026-08-10); read and write suites
  are green against both.

## Roadmap / next steps

1. **Verify prod-only field VALUES** (Igrins2/F2 offsets, saveSVCImages) -
   needs a token that can see F2/IGRINS2 observations; Dan's sees only his
   test program. Query text is already validated by production.
2. **GNIRS spectroscopy drift decision**: development restructured
   `GnirsSpectroscopy` (`centralWavelength`/`initialCentralWavelength` ->
   plural `[GnirsCentralWavelengthConfig!]!` lists, `coadds` removed), so
   those selections prune on development (schema refreshed 2026-08-11).
   Decide whether the operations should also select the new plural shape
   for dev consumers - a product call on what GOATS/scheduler need.
3. **Dev deployment stopped serving descriptions** (observed 2026-08-11):
   introspection against development returns null descriptions, so
   dev-only types lose their generated docstrings (shared types keep
   production's via the merge backfill). Upstream issue; re-download once
   fixed to restore them.
4. **site_status domain** (scrapes a status web page in the old client) -
   port if still wanted.
5. **Token hygiene**: Dan's prod token passed through a chat transcript;
   rotate it.
6. **Release**: the distribution is `gpp-client2` (Dan's decision,
   2026-08-10). Merge the `gpp-client2` release PR that release-please
   keeps open - it carries the version bump and changelog compiled from
   Conventional Commits, and the workflow publishes to PyPI (needs the
   one-time setup in the root CLAUDE.md roadmap).
