# The command line

Installing the package installs `gpp`. Every method on every domain is a
command, derived from the Python API by reflection at startup, so the two
surfaces cannot drift: `client.programs.get_by_id` is `gpp programs
get-by-id`, and a method added tomorrow is a command tomorrow.

```bash
gpp ping
gpp programs get-by-id --program-id p-123
gpp observations get-all --limit 10
```

Results print as JSON, showing the fields the operation actually fetched.
This page covers the usage patterns; the exhaustive command and option
listing, generated from the CLI itself, is in {doc}`cli-reference`, and
`gpp <group> --help` shows the same thing in the terminal.

## Choosing the deployment

Global options come before the command and mirror the client constructor;
whatever you do not pass resolves through the same chain of environment
variables and config-file profiles described in {doc}`configuration`:

```bash
gpp -e development programs get-all
gpp --profile prod ping
gpp --url http://localhost:8080 --schema development --token ... programs get-all
gpp --read-only observations get-all
```

## Passing arguments

Scalar parameters are ordinary options (`--program-id p-123`,
`--limit 10`). Enum parameters render their choices in `--help`. Boolean
parameters are flag pairs, and leaving a flag off means "not specified"
rather than false, so server defaults survive:

```bash
gpp programs get-all --include-deleted       # send true
gpp programs get-all --no-include-deleted    # send false
gpp programs get-all                         # send nothing
```

Input models are JSON options. Write them inline or point at a file with
`@`:

```bash
gpp programs create --properties '{"name": "New program"}'
gpp observations update-by-id --observation-id o-42 --properties @props.json
```

The JSON is validated against the input model before anything is sent, and
a validation failure is reported as a normal parameter error.

## Streaming

`watch-*` commands print one JSON document per event until you interrupt
them:

```bash
gpp programs watch-edits --program-id p-123
gpp scheduler watch-observation-updates --executable-only
```

## Raw GraphQL

The escape hatch works from the shell too. The query and the variables both
accept the `@file` form:

```bash
gpp graphql 'query { programs(LIMIT: 1) { matches { id name } } }'
gpp graphql @query.graphql --variables @vars.json
```

## Exit codes

Commands exit 0 on success and 1 on any client error, with the message on
stderr, so the output stream stays clean JSON for piping into `jq` and
friends.
