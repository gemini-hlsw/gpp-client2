# Getting started

## Install

```bash
pip install gpp-client2
```

or, with uv:

```bash
uv add gpp-client2
```

The distribution is `gpp-client2`, the import is `gpp_client2`, and the
command is `gpp2`. Nothing collides with the original `gpp-client`, so the
two generations can be installed side by side. Python 3.11 or newer is
required.

## Your first query

You need a GPP API token. Pass it directly for a first test, then move it
into a profile or an environment variable (see {doc}`configuration`) so it
stays out of your code.

```python
from gpp_client2 import GPPClient

with GPPClient(environment="production", token="your-token") as gpp:
    result = gpp.programs.get_all(limit=5)
    for program in result.matches:
        print(program.id, program.name)
```

`environment` accepts `"development"`, `"staging"`, or `"production"`, in
any case. The client refuses to guess: with no environment and no URL it
raises `GPPConfigError` instead of silently picking production.

To check that your setup works without running a real query:

```python
ok, reason = gpp.ping()
```

`ping()` returns `(True, None)` when the deployment is reachable and the
token is accepted, and `(False, reason)` otherwise.

## The async client

`AsyncGPPClient` has the same constructor and the same methods; every
operation is a coroutine.

```python
from gpp_client2 import AsyncGPPClient

async with AsyncGPPClient(environment="production", token="your-token") as gpp:
    program = await gpp.programs.get_by_id("p-123")
```

The two surfaces are identical by construction, and a test suite holds them
together. Anything you learn about one applies to the other.

## A safety net for read-heavy work

If a script or notebook only reads, say so:

```python
gpp = GPPClient(environment="production", token="...", read_only=True)
```

A read-only client raises `ReadOnlyError` before any network call when
something attempts a mutation, including attachment uploads and deletes
over REST. Subscriptions still work; they are reads.

## Where to go next

- {doc}`configuration` gets the token out of your code.
- {doc}`reading` explains the result models, including the `UNSET`
  sentinel you will meet immediately.
- {doc}`cli` does all of the above from the shell.
