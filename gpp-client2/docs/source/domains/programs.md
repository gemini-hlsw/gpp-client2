# Programs

The standard verbs (`get_by_id`, `get_all`, `create`, `update_by_id`,
`delete_by_id`, `restore_by_id`) plus the `watch_edits` subscription
stream. Deletes are soft everywhere (see {doc}`../writing`).

The same methods are CLI commands: {doc}`../cli/programs`.

## API

```{eval-rst}
.. autoclass:: gpp_client2.domains.ProgramAPI
   :members:
   :inherited-members:
```
