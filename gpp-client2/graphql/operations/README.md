# The operations tree

Every GraphQL selection the client can make lives here, as plain
`.graphql` files. This is the product: edit these files and regenerate,
and the Python API, the per-environment query texts, and the CLI all
follow.

## Folder = domain = client attribute

Each directory is one domain and becomes one client attribute:
`program/` → `client.programs`, `goats/` → `client.goats`,
`scheduler/` → `client.scheduler`, and so on. Directories starting with
`_` (like `_shared/`) hold fragments only and never become domains.

## Adding a query to an existing domain

Drop it in that domain's directory (any `.graphql` file there works;
`queries.graphql` by convention), named `<verb><Resource>[By<Key>]` -
`getProgramById`, `createTarget`, `updateObservationsByIds` - so the
method name derives automatically. Then:

```bash
uv run gqlforge generate
```

and commit the source together with the regenerated output. No wiring:
the method appears on both clients and as a CLI command.

Document an operation with a `#` comment block directly above it - it
becomes the generated method's docstring (see the `watch*`
subscriptions for examples). Leave a blank line after file-header
comments so they stay unattached.

Write the union of selections across all environments - gqlforge prunes
each environment's query text to what that environment can serve, fails
the build on a field no environment serves, and records who serves what
in `graphql/availability.json`.

## Adding a whole new domain

```bash
uv run gqlforge scaffold <domain>
```

creates the directory and the hand-written module, then prints the
wiring steps; the conformance tests fail until they're done.
