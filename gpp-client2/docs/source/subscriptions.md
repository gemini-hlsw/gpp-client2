# Streaming events

Subscriptions push server events to you over a WebSocket. Every
subscription is a `watch_*` method, and the two clients expose it the same
way: the sync client returns an iterator, the async client an async
iterator.

```python
for event in gpp.programs.watch_edits(program_id="p-123"):
    print(event.edit_type, event.value.name)
```

```python
async for event in gpp.observations.watch_calculations(program_id="p-123"):
    print(event.old_calculation_state, event.new_calculation_state)
```

Note that in the async client you do not `await` the call itself; calling
it returns the async iterator you then `async for` over.

## What you can watch

The summaries below come from the methods' own docstrings, which codegen
derives from the server's schema descriptions:

```{eval-rst}
.. autosummary::

   gpp_client2.domains.ProgramAPI.watch_edits
   gpp_client2.domains.ObservationAPI.watch_edits
   gpp_client2.domains.ObservationAPI.watch_calculations
   gpp_client2.domains.TargetAPI.watch_edits
   gpp_client2.domains.SchedulerAPI.watch_observation_updates
```

Each event carries an `edit_type` (`CREATED`, `UPDATED`, or `HARD_DELETE`)
and a `value` holding the affected item, parsed into the same models the
query methods return. The filter arguments are optional; without them you
receive events for everything your token can see. Full signatures are in
the {doc}`api`.

## Lifecycle

Each call opens its own WebSocket connection (`wss://<host>/ws`,
authenticated with your token). The iterator yields until one of three
things happens:

- you stop iterating (`break`, or close the generator), which closes the
  connection;
- the server completes the subscription, which ends iteration normally;
- the connection drops, which raises `GPPConnectionError` from inside the
  loop.

There is no automatic reconnect, deliberately: events that occurred while
you were disconnected are gone, and only your application knows whether
that matters. If it does, re-fetch current state with the matching `get_*`
method before trusting a re-opened stream:

```python
while True:
    try:
        for event in gpp.programs.watch_edits(program_id="p-123"):
            handle(event)
        break  # server completed the subscription
    except GPPConnectionError:
        refresh_from(gpp.programs.get_by_id("p-123"))
```

## Details that occasionally matter

Availability is checked when you call the method, not when you start
iterating, so an operation your environment cannot serve raises
`GPPOperationUnavailableError` immediately. Events follow the same
partial-response rule as queries: an event whose root survived is yielded
(with a warning logged), one whose every root field is null raises
`GPPGraphQLError`. Subscriptions count as reads, so they work on
`read_only=True` clients. And the iterators block while waiting, which is
the point; run them in a task or thread if you have other work to do.
