# Errors

Everything the client raises inherits from `GPPError`, so one `except`
catches it all when that is what you want. The subclasses tell you whose
problem it is.

| Exception | Raised when |
| --- | --- |
| `GPPConfigError` | Configuration cannot be resolved: unknown profile, unknown environment, no URL. |
| `GPPAuthError` | No token could be resolved, or the server rejected it (HTTP 401/403, WebSocket close 4401/4403). |
| `GPPConnectionError` | The deployment cannot be reached, or a subscription connection dropped. |
| `GPPTimeoutError` | A request or WebSocket connect timed out. Subclass of `GPPConnectionError`. |
| `GPPResponseError` | GPP returned a non-success HTTP status. Carries `status_code` and the response text. |
| `GPPGraphQLError` | Every root field of a response was null. Carries the raw error list in `.errors`. |
| `GPPOperationUnavailableError` | The operation does not exist in the active environment. Names the environments where it does. |
| `GPPFieldUnavailableError` | A raw query selects a field the active environment does not serve. |
| `GPPReadOnlyError` | A mutation (GraphQL or REST) was attempted on a `read_only=True` client. Raised before any network call. |
| `GPPRetryableError` | A transient condition worth retrying, such as a workflow update while the background calculation runs. |
| `GPPValidationError` | Inputs failed client-side validation before any request. |

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
from gpp_client import GPPClient
from gpp_client.errors import (
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
