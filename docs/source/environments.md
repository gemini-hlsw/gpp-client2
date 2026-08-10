# Environments

GPP runs several deployments: development, staging, and production. They
are almost, but not exactly, alike: development usually runs newer server
code, so at any moment some fields exist in one deployment and not another,
in both directions.

gpp-client2 ships one package that knows about all of them. The deployment
is a runtime choice, and the client sends query text generated specifically
for the schema that deployment serves.

## What pruning means for you

For every operation, the package carries one variant of the query text per
schema. A field that only one environment serves is simply absent from the
text sent to the others. The practical consequence: a divergent field never
causes an error; it comes back `UNSET`, exactly like a field the operation
does not select.

This is silent by design, and there is a direct way to ask instead of
debugging a mysteriously missing value:

```python
client.supports("ObservingMode.gnirsImaging")  # a Type.field pair
client.supports("getProgramById")  # an operation name
client.supports("programs.get_all")  # a domain method
```

Whole operations can also be environment-specific. Calling one where it
does not exist raises `GPPOperationUnavailableError`, and the error names
the environments where the operation does work.

Raw queries (see {doc}`raw-graphql`) get a lighter check: field names whose
availability is restricted and unambiguous are pre-flighted, and everything
else is left for the server to judge.

## Staging

Staging is registered but has no deployment URL yet. Until one exists,
constructing a client with `environment="staging"` raises `GPPConfigError`
telling you to pass a URL; when the deployment appears, it becomes one more
runtime choice with no package change on your side. Its query text follows
the production schema until it has a schema of its own.

## Keeping up with schema changes

The package pins the schemas it was generated against, and a nightly job
regenerates against the live deployments, so divergence shows up as an
ordinary pull request rather than a runtime surprise. As a user you only
ever see this as new package releases.
