# Domains in depth

The client groups its methods by resource: `gpp.programs`,
`gpp.observations`, `gpp.targets`, `gpp.attachments`,
`gpp.calls_for_proposals`, `gpp.goats`, `gpp.scheduler`, and
`gpp.workflow_state`. Most of them are the standard verbs covered in
{doc}`reading` and {doc}`writing`; this page covers the parts that go
beyond them.

## Attachments

Metadata is GraphQL; the file contents move over REST with presigned URLs,
and the client hides that split:

```python
attachment_id = gpp.attachments.upload(
    "p-123",
    attachment_type="SCIENCE",
    file_name="finder.pdf",
    file_path="~/finder.pdf",  # or content=b"..." for in-memory data
)
gpp.attachments.download_by_id(attachment_id, save_to="~/Downloads")
url = gpp.attachments.get_download_url_by_id(attachment_id)
```

Downloads stream, so large files do not load into memory. The presigned
download URL is served to you authenticated, but the URL itself can be
fetched without credentials until it expires; treat it accordingly.
Metadata queries exist per program, observation, and proposal reference
(`get_by_program_id`, `get_by_observation_reference`, and so on), and
`update_by_id` and `delete_by_id` manage what you uploaded.

## Workflow states

Observation workflow transitions are validated server-side, and the
interesting failure mode is timing: right after an edit, the server's
background calculation briefly cannot say which transitions are legal.

- `get_by_observation_id` / `get_by_observation_reference` read the
  current state, including `validTransitions`.
- `set_by_observation_id` writes a state with no questions asked.
- `update_by_observation_id` checks the requested state against
  `validTransitions` first, short-circuits when the state is already set,
  and raises `GPPRetryableError` while the calculation is still running.
- `update_by_observation_id_with_retry(max_attempts=, retry_delay=)` does
  the same and absorbs the retryable window for you.

```python
from gpp_client._generated.enums import ObservationWorkflowState

gpp.workflow_state.update_by_observation_id_with_retry(
    "o-123", state=ObservationWorkflowState.READY
)
```

## Scheduler

The scheduler domain serves the Gemini Scheduler service and anyone who
wants the same view of the data:

- `get_programs(programs_list=)`, `get_program_ids`, and
  `get_all_reference_labels(date=)` are plain queries.
- `atom_digests(observation_ids)` returns the REST atom-digest report as
  TSV text; `visibility_changes(since=)` returns typed
  `VisibilityChange` rows.
- `get_all()` assembles the full picture: each program as a dict with its
  `root` group tree, observation data, and atom sequences, trimmed to
  READY and ONGOING observations. This one returns dicts rather than
  models; its shape is the Scheduler service's consumption contract.
- `watch_observation_updates(executable_only=)` streams calculation-state
  changes (see {doc}`subscriptions`).

## GOATS

`gpp.goats.get_programs()` and `gpp.goats.get_observations(program_id)`
return the bulk shapes the GOATS tool consumes: wide selections tuned for
ingesting many items at once rather than inspecting one.

## Programs, observations, targets, calls for proposals

These follow the shared conventions, with a few domain-specific extras:
`observations.clone`, `targets.clone`, targets created through
`create_by_program_id`, `create_by_program_reference`, or
`create_by_proposal_reference`, and the `watch_*` subscriptions listed in
{doc}`subscriptions`. Deletes are soft everywhere (see {doc}`writing`).
