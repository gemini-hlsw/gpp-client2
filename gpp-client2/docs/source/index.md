# gpp-client2

gpp-client2 is a Python client for the Gemini Program Platform (GPP). It
covers the whole API: programs, observations, targets, attachments, calls
for proposals, scheduler data, and observation workflow states, over
GraphQL, REST, and WebSocket subscriptions.

It is the second generation of the GPP client, redesigned from scratch.
One package talks to any GPP
deployment. Which one, development, staging, or production, is a choice you
make at runtime, not at install time.

```python
from gpp_client2 import GPPClient

with GPPClient(environment="production", token="...") as gpp:
    program = gpp.programs.get_by_id("p-123")
    print(program.name)
```

Every operation returns a typed pydantic model, every method exists in a
sync and an async form, and every method is also a shell command:

```bash
gpp2 programs get-by-id --program-id p-123
```

## Where to start

If you have never used the client, read {doc}`getting-started`, then
{doc}`configuration`. The three task guides, {doc}`reading`,
{doc}`writing`, and {doc}`subscriptions`, cover almost everything you will
do day to day. {doc}`cli` covers the same ground from the shell.

When something behaves in a way you did not expect, {doc}`errors` and
{doc}`environments` are the two pages most likely to explain why.

```{toctree}
:hidden:
:maxdepth: 1
:caption: Guides

getting-started
configuration
reading
writing
subscriptions
cli
```

```{toctree}
:hidden:
:maxdepth: 1
:caption: Understanding the client

environments
domains/index
errors
raw-graphql
ai-agents
```

```{toctree}
:hidden:
:maxdepth: 1
:caption: Reference

api
enums
inputs
models
cli/index
contributing
changelog
```
