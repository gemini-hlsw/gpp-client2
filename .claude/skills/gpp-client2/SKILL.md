---
name: gpp-client2
description: Use the gpp-client2 Python library to query and update the Gemini Program Platform (GPP) - programs, observations, targets, attachments, calls for proposals, scheduler data, and observation workflow states - against any GPP environment. Use whenever writing Python that talks to GPP.
---

# Using gpp-client2

`tests/test_skill_doc.py` enforces that this file names every client
attribute and public method - update it in the same change as any API change.

## Construct a client

```python
from gpp_client2 import GPPClient, AsyncGPPClient

with GPPClient(environment="development", token="...") as gpp:  # sync
    ...
async with AsyncGPPClient(profile="prod") as gpp:  # async twin
    ...
```

Both clients accept the same keyword arguments: `environment`, `profile`,
`url` (local ODB; add `schema=` to pick query text), `token`,
`read_only=True` (refuses mutations before any network call - default for
analysis notebooks against production), `timeout`, and `transport` (inject
`httpx.MockTransport` in tests). Configuration resolves explicit args >
`GPP_*` env vars (`GPP_ENVIRONMENT`, `GPP_URL`, `GPP_TOKEN`, `GPP_PROFILE`)
> the profile from `config.toml` in the platform config dir
(`typer.get_app_dir("gpp-client2")`; `GPP_CONFIG_FILE` overrides):

```toml
default_profile = "dev"
[profiles.dev]
environment = "development"
token = "..."
```

No silent fallback: unresolvable config raises `GPPConfigError`/
`GPPAuthError` naming what is configured. `client.ping()` returns
`(ok, reason)`.

## Results: typed models with UNSET

Every method returns pydantic models. A field the operation did not select
(or the environment cannot serve) is the `UNSET` sentinel - distinct from a
server-returned `None`. `UNSET` is falsy; narrow with `is_set`:

```python
from gpp_client2 import UNSET, is_set

program = gpp.programs.get_by_id("p-123")  # -> Program | None
if is_set(program.description) and program.description:
    ...
```

`get_all` methods return a `*SelectResult` with `.matches` and `.has_more`;
pass `where=`, `limit=`, `offset=`, `include_deleted=` to page and filter.
Inputs (from `gpp_client2._generated.inputs`) send only explicitly set
fields, so "omitted" and "explicitly null" keep GraphQL semantics:

```python
from gpp_client2._generated.inputs import ProgramPropertiesInput, WhereProgram

gpp.programs.update_by_id("p-1", properties=ProgramPropertiesInput(description=None))
```

Enums live in `gpp_client2._generated.enums`; models in
`gpp_client2._generated.models`.

## Domains and methods

- `client.programs`: `create`, `get_by_id`, `get_by_reference`,
  `get_by_proposal_reference`, `get_all`, `update_by_id`, `update_all`,
  `delete_by_id`, `restore_by_id` (deletes are soft: `existence` flips), and
  the subscription `watch_edits(program_id=)`.
- `client.observations`: `create`, `clone`, `get_by_id`, `get_by_reference`,
  `get_all`, `update_by_id`, `update_by_reference`, `update_all`,
  `delete_by_id`, `delete_by_reference`, `restore_by_id`,
  `restore_by_reference`, and the subscriptions `watch_edits(program_id=)`
  and `watch_calculations(program_id=)`.
- `client.targets`: `create_by_program_id`, `create_by_program_reference`,
  `create_by_proposal_reference`, `clone`, `get_by_id`, `get_all`,
  `update_by_id`, `update_all`, `delete_by_id`, `restore_by_id`, and the
  subscription `watch_edits(target_id=)`.
- `client.calls_for_proposals`: `create`, `get_by_id`, `get_all`,
  `update_by_id`, `update_all`, `delete_by_id`, `restore_by_id`.
- `client.attachments`: metadata via `get_by_program_id`,
  `get_by_program_reference`, `get_by_proposal_reference`,
  `get_by_observation_id`, `get_by_observation_reference`; content via REST:
  `upload(program_id, attachment_type=..., file_name=..., file_path=|content=)`
  -> id, `update_by_id`, `delete_by_id`, `get_download_url_by_id`, and
  `download_by_id(id, save_to=...)` which streams the presigned URL
  unauthenticated.
- `client.workflow_state`: `get_by_observation_id`,
  `get_by_observation_reference`, raw `set_by_observation_id`, and the
  guarded `update_by_observation_id` /
  `update_by_observation_id_with_retry(max_attempts=, retry_delay=)` which
  validate against `validTransitions`, short-circuit when already set, and
  raise `GPPRetryableError` while the background calculation runs.
- `client.scheduler`: `get_programs(programs_list=)`, `get_program_ids`,
  `get_all_reference_labels(date=)`, REST `atom_digests(observation_ids)`
  (TSV) and `visibility_changes(since=)` (-> `list[VisibilityChange]`),
  `get_all()` - programs as dicts with a `root` group tree, observation data,
  and atom `sequence`s, trimmed to READY/ONGOING observations - and the
  subscription `watch_observation_updates(executable_only=)`.
- `client.goats`: `get_programs`, `get_observations(program_id)` - the bulk
  shapes the GOATS tool consumes.

## Subscriptions

`watch_*` methods stream server events over graphql-transport-ws
(`wss://<host>/ws`). The sync client returns an `Iterator`, the async client
an `AsyncIterator` - same names, same arguments:

```python
for event in gpp.programs.watch_edits(program_id="p-123"):  # sync
    print(event.edit_type, event.value.name)

async for event in gpp.observations.watch_calculations(program_id="p-123"):
    ...  # async: iterate with `async for` (no await on the call itself)
```

Each call opens its own WebSocket connection, closed when iteration ends.
Iteration ends normally only when the server completes the subscription;
a dropped connection raises `GPPConnectionError` mid-iteration, and there
is no automatic reconnect - long-running consumers decide their own retry
policy by re-calling the method. Subscriptions are reads: they work on
`read_only=True` clients. Environment availability is checked at the call
site (before connecting), like every generated operation.

## Environments and availability

The active environment is chosen at runtime; per-environment query text is
generated, so a field only one environment serves is simply pruned
elsewhere. Check before relying on divergent pieces:

```python
client.supports("ObservingMode.gnirsImaging")  # Type.field pair
client.supports("getProgramById")  # operation name
```

Unavailable operations raise `GPPOperationUnavailableError` naming where
they DO work; raw queries pre-flight restricted field names with
`GPPFieldUnavailableError`.

## Escape hatch

```python
data = gpp.graphql(
    "query($id: ObservationId!) { observation(observationId: $id) { title } }",
    variables={"id": "o-123"},
)  # dict result, server judges
```

Promote a stable query by dropping it in `gpp-client2/graphql/operations/<domain>/` and
running `uv run gqlforge generate`.

## CLI

Every domain method is also a shell command, derived by reflection:
`client.programs.get_by_id` is `gpp2 programs get-by-id --program-id p-123`.
Input models become JSON options (`--properties '{"name": "X"}'` or
`--properties @file.json`), `watch-*` commands stream JSON events, and
`gpp2 graphql` is the raw escape hatch. Global options mirror the client
constructor: `-e/--environment`, `--profile`, `--url`, `--token`,
`--read-only`.

## Errors

All inherit `GPPError`: `GPPConfigError`, `GPPAuthError` (401/403 or no
token), `GPPConnectionError`/`GPPTimeoutError`, `GPPResponseError` (HTTP),
`GPPGraphQLError` (all root fields null), `GPPOperationUnavailableError`,
`GPPFieldUnavailableError`, `GPPReadOnlyError`, `GPPRetryableError`,
`GPPValidationError`. Partial responses (data plus field-level errors, e.g.
a just-created observation whose background calculation has not run) return
the data and log a warning instead of raising.

## Scalars

IDs and labels are `str`; `Timestamp` fields parse to timezone-aware
`datetime` and serialize as ISO-8601 `Z`; `Date` is `datetime.date`; numeric
scalars are `int`/`float`. Naive datetimes passed as inputs are assumed UTC.

## Gotchas

Each of these was observed against real deployments; every one has a
regression test.

- **Truthiness conflates three states.** `if program.name:` is false for
  `UNSET` (not selected), `None` (server null), and `""`. When the
  distinction drives logic, test `is_set(x)` first, then `is None`.
- **Unselected fields type-check but are UNSET at runtime.** Models declare
  natural types (`id: str`), so nothing warns you statically that this
  operation never selected the field. `repr(model)` shows only set fields -
  print it when unsure what an operation returns.
- **Fresh observations have null calculated fields.** Immediately after
  `observations.create(...)`, `workflow` and `execution` come back `None`
  with a logged warning - the server's background calculation has not run.
  Do not treat that as failure; for state transitions use
  `workflow_state.update_by_observation_id_with_retry(...)`.
- **One broken row never fails a listing.** `get_all` returns partial data
  plus a warning when any single match has a server-side data problem (its
  errored subtree is `None`). Code iterating matches must tolerate `None`
  subtrees; do not assume the whole page is complete.
- **`Input(field=None)` clears the value; omitting the field leaves it
  untouched.** Update semantics live entirely in this distinction. Never
  pass `None` "for completeness".
- **Mutating an input after construction counts as set.** `props.name = "x"`
  adds `name` to the serialized payload just like passing it at
  construction.
- **Deletes are soft.** `delete_by_id` sets `existence=DELETED`; default
  queries then hide the item (`include_deleted=False`), which can look like
  data loss. `restore_by_id` undoes it.
- **`update_by_id`/`delete_by_id`/`restore_by_id` return bulk results.**
  They are `updateX(LIMIT: 1)` underneath: index `result.programs[0]`
  (`.targets[0]`, `.observations[0]`, `.calls_for_proposals[0]`).
- **`scheduler.get_all()` returns dicts, not models** - the Scheduler
  service's consumption contract. Everything else returns pydantic models.
- **Environment-divergent fields prune silently.** A production client's
  queries simply never contain dev-only fields (they stay `UNSET`), and
  vice versa. Check `client.supports("Type.field")` instead of debugging a
  mysteriously-UNSET field. Unavailable whole operations raise
  `GPPOperationUnavailableError` at call time, not import time.
- **`read_only=True` blocks REST writes too** (attachment upload/update/
  delete), not just GraphQL mutations - all raise `GPPReadOnlyError` before
  any network call.
- **Interface/union-typed responses always carry `__typename`** (codegen
  injects it). When building mock fixtures for tests, include it -
  discriminated-union parsing fails without it.
- **`watch_*` iterators are unbounded and blocking.** They yield forever
  until the server completes the subscription; `break` when done (that
  closes the connection). Partial-response semantics apply per event: an
  event whose root survived yields with a warning, one with every root
  null raises `GPPGraphQLError`.
- **A dropped subscription raises `GPPConnectionError`; events during a
  gap are gone.** There is no replay on reconnect - after re-calling
  `watch_*`, re-fetch current state with the corresponding `get_*` before
  trusting the stream again.

## Contributing to this repository

When changing gpp-client2 itself (not just using it), two process rules
apply on top of the hard rules in the root and per-project CLAUDE.md
files:

- Any user-visible change needs a towncrier fragment in the changed project's `changelog.d/`
  (`gpp-client2/changelog.d/` or `gqlforge/changelog.d/`)
  (`+<slug>.<type>.md`, types `feat|fix|perf|docs|removal|misc`) in the
  same commit. `CHANGELOG.md` is compiled by towncrier - never edit it
  directly.
- Commit messages follow Conventional Commits (`type(scope): summary`).
