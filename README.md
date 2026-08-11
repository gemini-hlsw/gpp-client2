# gpp-client2 monorepo

Two Python projects developed together, released separately:

| Project | What it is | Docs |
| --- | --- | --- |
| [`gpp-client2/`](gpp-client2/) | Client for the Gemini Program Platform: one package, any GPP deployment as a runtime choice, dual sync/async API, `gpp2` CLI | [gpp-client2.readthedocs.io](https://gpp-client2.readthedocs.io) |
| [`gqlforge/`](gqlforge/) | The multi-schema GraphQL-to-Python codegen that produces gpp-client2's generated layer - usable by any project with the same shape | [gqlforge.readthedocs.io](https://gqlforge.readthedocs.io) |

gpp-client2 is gqlforge's reference consumer: every gqlforge feature is
exercised in production by the client build. They share one uv
workspace (one lockfile, one virtualenv) and one CI.

## Working in the monorepo

```bash
uv sync                      # once, at the root - sets up both projects
cd gpp-client2 && uv run pytest        # client suite
cd gqlforge   && uv run pytest        # codegen suite
uv run ruff check .          # lint everything, from anywhere
```

Each project's README and docs are the authoritative guide for working
inside it. Repo-wide conventions (Conventional Commits, towncrier
changelog fragments, the generated-code rules) are in `CLAUDE.md`.
