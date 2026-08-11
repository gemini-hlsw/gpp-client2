# GOATS

Bulk shapes the GOATS tool ingests: `get_programs()` and
`get_observations(program_id)` return wide selections tuned for reading
many items at once. The selections are plain GraphQL in
`graphql/operations/goats/queries.graphql`; adding or removing a field
is an edit plus a regenerate ({doc}`../contributing`).

The same methods are CLI commands: {doc}`../cli/goats`.

## API

```{eval-rst}
.. autoclass:: gpp_client2.domains.GoatsAPI
   :members:
   :inherited-members:
```
