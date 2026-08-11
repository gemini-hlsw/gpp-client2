# Scheduler

Serves the Gemini Scheduler service and anyone wanting the same view:

- `get_programs(programs_list=)`, `get_program_ids`, and
  `get_all_reference_labels(date=)` are plain queries.
- `atom_digests(observation_ids)` returns the REST atom-digest report
  as TSV; `visibility_changes(since=)` returns typed rows.
- `get_all()` assembles each program's group tree with observation data
  and atom sequences, trimmed to READY and ONGOING observations. It
  returns dicts - the shape is the Scheduler service's contract.
- `watch_observation_updates(executable_only=)` streams
  calculation-state changes ({doc}`../subscriptions`).

The selections live in `graphql/operations/scheduler/`
({doc}`../contributing` covers changing them).

The same methods are CLI commands: {doc}`../cli/scheduler`.

## API

```{eval-rst}
.. autoclass:: gpp_client2.domains.SchedulerAPI
   :members:
   :inherited-members:
```
