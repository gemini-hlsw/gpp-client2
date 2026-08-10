# Reading data

Every read method returns pydantic models. This page explains the three
things about those models that are worth understanding before you write any
real code: the `UNSET` sentinel, paging, and partial responses.

## Getting one thing

Single-item lookups exist for each identifier a resource has:

```python
program = gpp.programs.get_by_id("p-123")
program = gpp.programs.get_by_reference("G-2025B-1234")
observation = gpp.observations.get_by_reference("G-2025B-1234-0001")
```

They return the model, or `None` when nothing matches.

## Getting many things

`get_all` methods page through matches and take the same filter arguments
the GraphQL API does:

```python
result = gpp.observations.get_all(limit=50)
for observation in result.matches:
    print(observation.id, observation.title)
if result.has_more:
    next_page = gpp.observations.get_all(limit=50, offset=result.matches[-1].id)
```

`where=` accepts a typed filter input (see {doc}`writing` for how inputs
work), `include_deleted=True` includes soft-deleted items, and `offset=`
starts the page after a given id.

## UNSET: the third state

A model field can be in three states, and two of them look similar until
they bite:

- a real value: the operation selected the field and the server returned it,
- `None`: the operation selected the field and the server returned null,
- `UNSET`: the operation never selected the field at all.

Models declare natural types (`name: str`), so nothing warns you statically
that a particular operation never fetches a field. At runtime the
difference is visible:

```python
from gpp_client import UNSET, is_set

program = gpp.programs.get_by_id("p-123")
if is_set(program.description):
    ...  # the query fetched it; it may still be None
```

`UNSET` is falsy, so `if program.description:` is safe when you only care
whether there is a usable value. When your logic depends on *why* there is
no value, test `is_set()` first and `is None` second.

`repr(model)` prints only the fields that are set, which makes it the
quickest way to see what a given operation actually returns.

## Partial responses

GraphQL can return data and errors at the same time. The client follows the
protocol's semantics: an operation has failed only when every root field is
null, and that raises `GPPGraphQLError`. Anything less than total failure
returns the data and logs a warning.

This matters in practice. One broken observation in a 200-row listing nulls
out its own subtree and nothing else; a freshly created observation reports
errors on its background-calculated fields for a few seconds. In both cases
you get the data that exists. Code that iterates over matches should
tolerate a `None` subtree rather than assume every row is complete.

## Timestamps and scalars

IDs and labels are strings. `Timestamp` fields parse to timezone-aware
`datetime` objects and serialize back as ISO-8601 UTC with a `Z` suffix.
`Date` fields are `datetime.date`. A naive `datetime` you pass as input is
assumed to be UTC.
