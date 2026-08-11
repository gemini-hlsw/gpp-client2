# Observations

The standard verbs plus `clone`, and two subscription streams:
`watch_edits` and `watch_calculations`. Workflow-state transitions live
in their own domain, {doc}`workflow-state`.

The same methods are CLI commands: {doc}`../cli/observations`.

## API

```{eval-rst}
.. autoclass:: gpp_client2.domains.ObservationAPI
   :members:
   :inherited-members:
```
