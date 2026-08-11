# Workflow states

Transitions are validated server-side, and the interesting failure
mode is timing: right after an edit, the background calculation briefly
cannot say which transitions are legal.

- `get_by_observation_id` / `get_by_observation_reference` read the
  current state, including `validTransitions`.
- `set_by_observation_id` writes with no questions asked.
- `update_by_observation_id` checks `validTransitions` first,
  short-circuits when already set, and raises `GPPRetryableError`
  while the calculation runs.
- `update_by_observation_id_with_retry(max_attempts=, retry_delay=)`
  absorbs the retryable window for you.

```python
from gpp_client2._generated.enums import ObservationWorkflowState

gpp.workflow_state.update_by_observation_id_with_retry(
    "o-123", state=ObservationWorkflowState.READY
)
```

The same methods are CLI commands: {doc}`../cli/workflow-state`.

## API

```{eval-rst}
.. autoclass:: gpp_client2.domains.WorkflowStateAPI
   :members:
   :inherited-members:
```
