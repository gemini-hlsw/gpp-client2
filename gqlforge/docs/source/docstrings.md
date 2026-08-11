# Docstrings

Generated code should carry real documentation, and authors should
never edit generated files to add it. Documentation flows from two
sources, by precedence.

## 1. Leading comment blocks on operations

A `#` comment block directly above an operation becomes that method's
docstring opening, verbatim and multi-line:

```graphql
# Fetch a widget by its identifier.
# Returns UNSET fields for anything not selected.
query getWidgetById($id: ID!) {
  widget(id: $id) {
    id
    name
  }
}
```

produces

```python
def get_widget_by_id(self, id: str) -> Widget | None:
    """
    Fetch a widget by its identifier.
    Returns UNSET fields for anything not selected.

    Parameters
    ----------
    ...
    """
```

A blank line breaks the attachment, so a file-header comment separated
from the first operation by one blank line is never mistaken for
documentation. This convention exists because GraphQL forbids `"""`
descriptions on executable operations - the comment block is the only
author-controlled channel the language leaves open.

## 2. Schema SDL descriptions

Everything else flows from the schema itself:

- Type descriptions become model class docstrings.
- Field descriptions become field documentation on the models.
- An operation with no comment block uses the schema's description of
  the root field it selects (e.g. `Query.widget`) as its summary, and
  falls back to a generic sentence when the schema is silent too.

## Derived sections

Parameter, return, and yield sections are always derived from the
operation's variables and return shape - numpydoc-formatted, with the
GraphQL variable name, type, and server-side default noted for every
parameter. Authors write the *why*; `gqlforge` writes the *signature*.
