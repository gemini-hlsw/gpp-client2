# gpp-client

Python client for the Gemini Program Platform (GPP).

One installable package that talks to any GPP deployment - development,
staging, or production - as a **runtime choice**. No environment-tagged
releases, no prerelease-channel gymnastics: `pip install gpp-client` works for
everyone, and which backend you talk to is decided when you construct the
client.

```python
from gpp_client import GPPClient

with GPPClient(environment="development", token="...") as gpp:
    program = gpp.programs.get_by_id("p-123")
    print(program.name)
```

Every operation returns a typed pydantic model. There is a sync client and an
async twin with an identical surface:

```python
from gpp_client import AsyncGPPClient

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
   `~/.config/gpp-client/config.toml`

There is no silent fallback to production; if nothing resolves, the error
names the profiles that are configured.

```toml
# ~/.config/gpp-client/config.toml
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
becomes a typed method on the next `codegen generate` - promotion to
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

## Development

```bash
uv sync                                  # install everything
uv run pytest                            # offline test suite
uv run ruff check . && uv run mypy       # lint + types
uv run python -m codegen generate        # regenerate after editing operations
uv run python -m codegen check           # CI: fail if artifacts are stale
uv run python -m codegen readiness       # can we promote yet?
uv run python -m codegen download        # refresh schemas (needs a token)
uv run python -m codegen scaffold <name> # start a new domain
uv run pytest -m live                    # read-only smoke tests, real deployment
GPP_LIVE_WRITE=1 uv run pytest -m live   # + write round-trips (see below)
```

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

`.github/workflows/live_tests.yaml` runs the read suite nightly and the
write suite on manual dispatch, using a `GPP_LIVE_TOKEN` secret.

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
codegen/             dev-only generator (merge, prune, emit) - not shipped
src/gpp_client/
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
2. `uv run python -m codegen generate`
3. Commit the source *and* generated changes; CI verifies they match.

### Adding a domain

`uv run python -m codegen scaffold <domain>` creates the skeleton and prints
the wiring steps; the conformance tests enforce completion.

### Adding an environment (e.g. staging goes live)

1. Set its URL in `src/gpp_client/environments.py`.
2. `uv run python -m codegen download staging`, flip its `schema_source`.
3. `uv run python -m codegen generate` and commit.

## Not yet ported from the original client

Subscriptions (GraphQL over WebSocket), the site-status page scraper, the
Typer CLI, and Sphinx docs. The architecture reserves their places:
subscriptions need a WebSocket transport beside the httpx one; the CLI can
derive from the same operation specs the domain bases come from.
