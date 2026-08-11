# Errors

Everything the client raises inherits from `GPPError`, so one `except`
catches it all when that is what you want. The subclasses tell you whose
problem it is. The full taxonomy below is rendered from the code, so it
always matches the installed version:

```{eval-rst}
.. automodule:: gpp_client2.errors
   :members:
   :show-inheritance:
   :no-index:
```

## When errors are not raised

The client deliberately does not raise on partial responses. A response
with data and errors returns the data and logs a warning; only a response
whose every root field is null raises `GPPGraphQLError`. The reasoning and
the practical consequences are in {doc}`reading`.

Two situations look like errors but are expected behavior:

- A field that is `UNSET` on a returned model was never selected by the
  operation, or is not served by your environment. Check
  `client.supports(...)` before suspecting a bug ({doc}`environments`).
- `workflow` and `execution` on a just-created observation are `None`
  while the server's background calculation runs. Use the retry helper in
  {doc}`domains` when you need to act on the result.

## A pattern that works

```python
from gpp_client2 import GPPClient
from gpp_client2.errors import (
    GPPAuthError,
    GPPConnectionError,
    GPPGraphQLError,
)

try:
    with GPPClient(profile="prod") as gpp:
        result = gpp.observations.get_all(limit=100)
except GPPAuthError:
    ...  # token missing, expired, or wrong environment
except GPPConnectionError:
    ...  # network problem; retrying later is reasonable
except GPPGraphQLError as exc:
    print(exc.errors)  # the server said no; the raw errors say why
```
