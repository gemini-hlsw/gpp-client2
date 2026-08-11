# Configuration

Both clients resolve their configuration the same way, field by field, from
three places. Higher entries win:

1. Explicit constructor arguments: `GPPClient(environment=..., token=...)`.
2. Environment variables: `GPP_ENVIRONMENT`, `GPP_URL`, `GPP_TOKEN`,
   `GPP_PROFILE`, `GPP_SCHEMA_SOURCE`.
3. The profile selected by `GPP_PROFILE`, or the `default_profile`, in the
   config file.

There is no silent fallback. When nothing resolves, the error names the
profiles that are configured so you can see what the client actually found.

## The config file

The file lives at `~/.config/gpp-client2/config.toml` (or under
`$XDG_CONFIG_HOME` if you set it; `$GPP_CONFIG_FILE` overrides the path
entirely). A profile bundles an environment with its token:

```toml
default_profile = "prod"

[profiles.dev]
environment = "development"
token = "..."

[profiles.prod]
environment = "production"
token = "..."
```

With this file in place, construction needs no arguments at all:

```python
gpp = GPPClient()  # uses default_profile
gpp = GPPClient(profile="dev")  # explicit profile
```

Switching your whole session to another deployment is one environment
variable:

```bash
export GPP_PROFILE=dev
```

## Pointing at a local ODB

For a locally running ODB, pass the URL directly. The client then needs to
know which query text to use, since a custom URL does not say which schema
the server speaks; it assumes the newest committed schema unless you pick
one:

```python
gpp = GPPClient(url="http://localhost:8080", schema="development", token="...")
```

## Everything the constructor takes

| Parameter | Meaning |
| --- | --- |
| `environment` | `"development"`, `"staging"`, or `"production"`, any case. |
| `profile` | Profile name from the config file. |
| `url` | Explicit base URL. Overrides the environment URL. |
| `schema` | Schema source to pair with a custom `url`. |
| `token` | GPP API token. |
| `read_only` | Refuse mutations before any network call. Default `False`. |
| `timeout` | Request timeout in seconds, also the WebSocket connect timeout. Default 30. |
| `transport` | A custom httpx transport, mainly for tests. |
| `config_path` | Read a specific config file instead of the default. |

`AsyncGPPClient` takes exactly the same parameters.
