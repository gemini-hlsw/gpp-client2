# Raw GraphQL

When the client does not ship the operation you need, write it yourself.
`graphql()` sends any operation text and returns the raw `data` dict:

```python
data = gpp.graphql(
    """
    query ($id: ObservationId!) {
      observation(observationId: $id) { title subtitle }
    }
    """,
    variables={"id": "o-123"},
)
print(data["observation"]["title"])
```

The async client's version is the same, awaited. Variables are serialized
with the same rules as generated operations, so input models, enums, and
datetimes all work. Multi-operation documents need `operation_name=`.

Nothing validates the text on your machine beyond a cheap pre-flight:
mutations are refused on read-only clients, and field names that codegen
knows to be environment-restricted raise `GPPFieldUnavailableError` before
the request goes out. Everything else is the server's call, which is the
point of an escape hatch.

## Promoting a query

A raw query that earns a permanent place in your code belongs in the
client. Drop the text into `graphql/operations/<domain>/` in the repository
and run `uv run python -m codegen generate`; it becomes a typed method on
both clients, a CLI command, and part of the conformance suite. See
{doc}`contributing`.
