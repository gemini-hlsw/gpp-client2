# gpp-client2

Python client for the Gemini Program Platform (GPP) - the second
generation, redesigned from scratch. Everything about it is versioned
separately from the original
client: the distribution is `gpp-client2`, the import is `gpp_client2`,
and the command is `gpp2`, so both generations install side by side.

One installable package that talks to any GPP deployment - development,
staging, or production - as a **runtime choice**. No environment-tagged
releases, no prerelease-channel gymnastics: `pip install gpp-client2` works
for everyone, and which backend you talk to is decided when you construct
the client.

```python
from gpp_client2 import GPPClient

with GPPClient(environment="development", token="...") as gpp:
    program = gpp.programs.get_by_id("p-123")
    print(program.name)
```

Every operation returns a typed pydantic model. There is a sync client and an
async twin with an identical surface:

```python
from gpp_client2 import AsyncGPPClient

async with AsyncGPPClient(profile="dev") as gpp:
    result = await gpp.observations.get_all(limit=10)
    for observation in result.matches:
        print(observation.id, observation.title)
```

## Configuration

Configuration resolves per field, highest priority first:

1. Explicit arguments: `GPPClient(environment=..., url=..., token=...)`
2. Environment variables: `GPP_ENVIRONMENT`, `GPP_URL`, `GPP_TOKEN`,
   `GPP_PROFILE`, `GPP_SCHEMA_SOURCE`
3. The profile selected by `GPP_PROFILE`, or `default_profile` from
   `config.toml` in the platform config dir (via `typer.get_app_dir`:
   `~/.config/gpp-client2/` on Linux, `~/Library/Application
   Support/gpp-client2/` on macOS, `%APPDATA%\`gpp-client2`\` on Windows)

There is no silent fallback to production; if nothing resolves, the error
names the profiles that are configured.

```toml
# config.toml in the platform config dir (see above)
default_profile = "dev"

[profiles.dev]
environment = "development"
token = "..."

[profiles.prod]
environment = "production"
token = "..."
```

Talking to two environments at once is just two clients, which is what makes
a promotion verifiable:

```python
async with (
    AsyncGPPClient(profile="dev") as dev,
    AsyncGPPClient(profile="prod") as prod,
):
    a, b = await asyncio.gather(
        dev.observations.get_by_id("o-123"),
        prod.observations.get_by_id("o-123"),
    )
```

A local ODB needs only a URL (query text defaults to the newest schema):

```python
GPPClient(url="http://localhost:8080", token="...")
```

### Guardrails

`GPPClient(profile="prod", read_only=True)` refuses to execute mutations
before anything touches the network - the natural default for analysis
notebooks pointed at the live observatory database.

## How environment differences work

The GPP environments genuinely diverge, in both directions: development is
ahead on new features *and* ahead on removals. This client handles that
without a per-environment build:

- **One operations tree.** `graphql/operations/` holds the union of every
  selection used anywhere. Nothing marks a field as environment-specific.
- **Derived per-environment queries.** Codegen prunes each operation against
  each committed schema. A field an environment cannot serve is dropped from
  that environment's query text only. A typo validates nowhere and fails the
  build.
- **One set of models,** generated from the merged (union) schema. A field
  the operation did not select - or the environment could not serve - is the
  `UNSET` sentinel, distinct from a server-returned `None`.
- **A committed availability manifest** (`graphql/availability.json`). When a
  field or operation becomes available in a new environment, the nightly
  schema-sync PR shows exactly that line changing. Merging it is the whole
  promotion ceremony.

At runtime the client picks the query text for its environment. Asking for
something the environment cannot serve produces a clear error naming where it
*is* available:

```python
client.supports("ObservingMode.gnirsImaging")  # False on production today
```

### Escape hatches

For queries the client does not ship, work up the ladder as needed:

```python
# Raw text: zero ceremony, dict result, the server is the judge.
data = gpp.graphql(
    "query($id: ObservationId!) { observation(observationId: $id) { title } }",
    variables={"id": "o-123"},
)
```

When a query stabilizes, drop it in `graphql/operations/<domain>/` and it
becomes a typed method on the next `gqlforge generate` - promotion to
first-class costs one file.

## Beyond CRUD

```python
tsv = gpp.scheduler.atom_digests(["o-1", "o-2"])  # REST
changes = gpp.scheduler.visibility_changes(since=datetime(2025, 8, 1))
tree = gpp.scheduler.get_all()  # assembled program tree

gpp.workflow_state.update_by_observation_id_with_retry(  # guarded transition
    "o-123", state=ObservationWorkflowState.READY
)

attachment_id = gpp.attachments.upload(  # REST content transfer
    "p-123",
    attachment_type="SCIENCE",
    file_name="finder.pdf",
    file_path="~/finder.pdf",
)
gpp.attachments.download_by_id(attachment_id, save_to="~/Downloads")
```

### Subscriptions

`watch_*` methods stream server events over GraphQL WebSocket
subscriptions (`graphql-transport-ws`). Sync iterates, async
`async`-iterates - same names, same arguments, same typed models:

```python
for event in gpp.programs.watch_edits(program_id="p-123"):
    print(event.edit_type, event.value.name)

async for event in gpp.observations.watch_calculations(program_id="p-123"):
    print(event.new_calculation_state)
```

Also available: `observations.watch_edits`, `targets.watch_edits`, and
`scheduler.watch_observation_updates(executable_only=True)` - the
calculation-state stream the Scheduler service consumes. Iteration ends
when the server completes the subscription; a dropped connection raises
`GPPConnectionError`, and reconnecting is the caller's decision (events
during a gap are not replayed).

### The CLI

Installing the package also installs `gpp2`. Every domain method is a
command, derived from the Python API by reflection, so the two surfaces
cannot drift:

```bash
gpp2 ping
gpp2 programs get-by-id --program-id p-123
gpp2 programs get-all --limit 5 --include-deleted
gpp2 programs create --properties '{"name": "New program"}'
gpp2 observations update-by-id --observation-id o-42 --properties @props.json
gpp2 programs watch-edits --program-id p-123   # streams JSON events
gpp2 graphql 'query { programs(LIMIT: 1) { matches { id } } }'
```

Input models are JSON options (inline or `@file.json`); global options
(`-e/--environment`, `--profile`, `--url`, `--token`, `--read-only`) mirror
the client constructor; results print as JSON.

## Development

This project is one member of a uv workspace; run `uv sync --all-packages`
once at the repository root, then run the commands below from this
directory (`gpp-client2/`).

| Command | What it does |
| --- | --- |
| `uv sync` | Install everything |
| `uv run pytest` | Offline test suite (fast, no network) |
| `uv run ruff check . && uv run mypy` | Lint and strict typing |
| `uv run gqlforge generate` | Regenerate after editing operations |
| `uv run gqlforge check` | CI: fail if committed artifacts are stale |
| `uv run gqlforge readiness` | Cross-environment promotion report |
| `uv run gqlforge download [env]` | Refresh schemas (needs a token) |
| `uv run gqlforge scaffold <name>` | Start a new domain |
| `uv run sphinx-build -W docs/source docs/_build` | Build the documentation |
| `uv run towncrier build --draft` | Preview the changelog compiled from `changelog.d/` |
| `uv run pytest -m live` | Read-only smoke tests against a real deployment |
| `GPP_LIVE_WRITE=1 uv run pytest -m live` | Also run write round-trips (see below) |

### Live testing

Two levels, both requiring a resolvable configuration (profile or
``GPP_TOKEN``):

- **Read-only** (`tests/test_live.py`): ping and `get_all` per domain. Runs
  with `-m live`; never writes.
- **Write round-trips** (`tests/test_live_roundtrip.py`): create -> update ->
  delete across programs, targets, and observations, including a Timestamp
  serialization round-trip. Requires the extra `GPP_LIVE_WRITE=1` opt-in.

The write suite is built to be safe to repeat:

- Hard creation budget: at most 2 items per domain, 50 total.
- Every created item's exact ID goes into `.live-test-ledger.json` (ignored
  by git) the moment it exists; deletion only ever targets recorded IDs.
- A leftover ledger from a crashed run is cleaned up at the start of the
  next, and a fully green run ends with the ledger gone and every created
  item existence=DELETED.
- Items carry neutral names with a per-run nonce (`Test program <nonce>`).

`.github/workflows/live_tests.yaml` runs nightly against development and
production in parallel (per-environment `GPP_DEV_TOKEN` / `GPP_PROD_TOKEN`
secrets): the read suite on both, the write suite on development.
Production writes run only on manual dispatch. An environment without a
configured token is skipped with a visible warning, never failed silently.
The companion `schema_sync.yaml` downloads every environment's schema
nightly, regenerates, and opens a PR when anything moved - so drift
between the committed schemas and reality becomes a reviewable diff, not
a surprise.

### Layout

```
graphql/
  operations/        THE product: what data each operation asks for
    _shared/         fragments used across domains
    program/         one directory per domain -> client.programs
    observation/     -> client.observations
    target/          -> client.targets
    attachment/      -> client.attachments (+ REST upload/download)
    call_for_proposals/  -> client.calls_for_proposals
    goats/           -> client.goats
    scheduler/       -> client.scheduler (+ REST files, assembled tree)
    workflow_state/  -> client.workflow_state (+ guarded transitions)
  schemas/           committed environment schemas + derived merged schema
  availability.json  what is available where (derived, committed, reviewed)
../gqlforge/         sibling workspace member: the codegen library
                     (merge, prune, emit), driven by [tool.gqlforge]
                     in this project's pyproject.toml
src/gpp_client2/
  _generated/        DO NOT EDIT - models, inputs, enums, operation map,
                     sync + async domain bases
  domains/           hand-written subclasses; curated helpers live here
  client.py          GPPClient / AsyncGPPClient
tests/               offline suite incl. conformance tests
```

Curated helpers layered on the generated coverage, in both sync and async
forms:

- `client.workflow_state.update_by_observation_id(...)` validates the
  transition against `validTransitions`, waits out the background
  calculation (`_with_retry` variant), and short-circuits when already set.
- `client.scheduler.get_all()` assembles each program's group tree with full
  observation data and atom-digest sequences - the shape the Scheduler
  service consumes.
- `client.attachments.upload / download_by_id / update_by_id / delete_by_id`
  speak the REST content endpoints; downloads stream the presigned URL with
  a bare, unauthenticated request.

### The conformance rule

Every operation in the tree must be reachable as a generated method on a
registered domain, with identical sync and async surfaces - enforced by
`tests/test_conformance.py`, so a coverage gap fails CI instead of waiting
for someone to notice.

### Adding an operation

1. Write it in `graphql/operations/<domain>/`, named
   `<verb><Resource>[By<Key>]` so its method name derives automatically.
2. `uv run gqlforge generate`
3. Commit the source *and* generated changes; CI verifies they match.
   Like any user-visible change, include a changelog fragment in
   `changelog.d/` (see `changelog.d/README.md`) and use a Conventional
   Commits message (`type(scope): summary`).

### Changing what an existing query selects

The selections behind every method - including the wide GOATS and
scheduler queries - are plain GraphQL files, not code. To add or remove
fields from, say, `goats.get_observations`, edit
`graphql/operations/goats/queries.graphql` (shared fragments live in
`graphql/operations/_shared/` and `<domain>/fragments.graphql`), run
`uv run gqlforge generate`, and commit both. The models and the
per-environment query texts follow automatically.

You do not have to think about which environments serve a new field -
`gqlforge` does:

- A field only development serves stays in development's query text and
  is pruned from staging's and production's. On those environments the
  model attribute is the `UNSET` sentinel; nothing breaks at runtime.
- A field no committed schema serves fails `gqlforge generate` - a typo
  cannot ship.
- The `graphql/availability.json` diff in the same commit shows exactly
  which environments serve the new field, and
  `uv run gqlforge readiness` reports when the rest catch up.

### Adding a domain

`uv run gqlforge scaffold <domain>` creates the skeleton and prints
the wiring steps; the conformance tests enforce completion.

### Adding an environment (e.g. staging goes live)

1. Set its URL in `src/gpp_client2/environments.py`.
2. `uv run gqlforge download staging`, flip its `schema_source`.
3. `uv run gqlforge generate` and commit.

## Not yet ported from the original client

The site-status page scraper (it screen-scrapes a status web page rather
than an API); everything else from the original client has a home here.
