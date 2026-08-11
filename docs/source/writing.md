# Writing data

Mutations take typed input models from `gpp_client2._generated.inputs`. The
single most important thing on this page is the difference between omitting
a field and setting it to `None`.

## Omitted is not null

GraphQL distinguishes "don't touch this field" from "clear this field", and
the input models preserve that distinction exactly. A field you never set
is not sent; a field you set to `None` is sent as null:

```python
from gpp_client2._generated.inputs import ProgramPropertiesInput

# Renames the program. description is not sent and stays as it was.
gpp.programs.update_by_id("p-123", properties=ProgramPropertiesInput(name="New name"))

# Clears the description.
gpp.programs.update_by_id("p-123", properties=ProgramPropertiesInput(description=None))
```

Never pass `None` "for completeness"; it is a write. Assigning to a field
after construction counts as setting it, so `props.name = "x"` puts `name`
into the payload just like passing it to the constructor.

## Creating

```python
from gpp_client2._generated.inputs import ProgramPropertiesInput

program = gpp.programs.create(properties=ProgramPropertiesInput(name="My program"))
print(program.id)
```

Create methods unwrap the response for you: `create()` returns a `Program`,
not a wrapper object. Fresh observations are a special case worth knowing
about: their background-calculated fields (`workflow`, `execution`) come
back `None` with a logged warning until the server's calculation catches
up. That is normal, not a failed create. See {doc}`reading` for the
partial-response rules and {doc}`domains` for the retry helper.

## Updating

Update methods are bulk operations underneath, even the by-id forms, so
their results have a bulk shape. `update_by_id` runs `updatePrograms` with
a one-item filter, and you index the result:

```python
result = gpp.programs.update_by_id(
    "p-123", properties=ProgramPropertiesInput(description="Updated")
)
updated = result.programs[0]
```

The same applies to `delete_by_id` and `restore_by_id`
(`result.observations[0]`, `result.targets[0]`, and so on), and to the
`update_all` forms, which take a `where=` filter and touch every match.

## Deleting is soft

`delete_by_id` does not remove anything. It flips the item's `existence`
to `DELETED`, after which default queries hide it, which can look like data
loss if you do not know to expect it. Pass `include_deleted=True` to see
such items, and `restore_by_id` to bring one back:

```python
gpp.programs.delete_by_id("p-123")
gpp.programs.get_by_id("p-123")  # None
gpp.programs.get_all(include_deleted=True)  # includes it
gpp.programs.restore_by_id("p-123")  # back to PRESENT
```

## Building nested inputs

Inputs nest like the API's own input types, and every layer keeps the
omit-vs-null rule:

```python
from gpp_client2._generated.inputs import (
    SiderealInput,
    TargetPropertiesInput,
)

properties = TargetPropertiesInput(
    name="M42",
    sidereal=SiderealInput(
        ra={"hms": "05:35:17.3"},
        dec={"dms": "-05:23:28.0"},
        epoch="J2000.000",
    ),
)
target = gpp.targets.create_by_program_id("p-123", properties=properties)
```

Where the API accepts either a structured object or a shorthand (like the
`ra` dict above), the input models accept both. Enums live in
`gpp_client2._generated.enums` and can be passed as members or as their
string values.
