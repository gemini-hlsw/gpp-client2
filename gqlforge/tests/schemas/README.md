# Corpus schemas

SDL snapshots of public GraphQL APIs, used by `test_corpus.py` to prove
gqlforge handles real-world schemas end to end - generation, importable
pydantic models, and pruning. They are fixtures, not dependencies: tests
never touch the network, and drift in the upstream APIs does not break
the suite.

| File | Source | Size | Fetched |
| --- | --- | --- | --- |
| `countries.graphql` | https://countries.trevorblades.com/ (introspection) | 1 KB | 2026-08-11 |
| `rickandmorty.graphql` | https://rickandmortyapi.com/graphql (introspection) | 4 KB | 2026-08-11 |
| `swapi.graphql` | https://swapi-graphql.netlify.app/graphql (introspection) | 35 KB | 2026-08-11 |
| `anilist.graphql` | https://graphql.anilist.co (introspection) | 147 KB | 2026-08-11 |
| `github.graphql` | https://docs.github.com/public/fpt/schema.docs.graphql | 1.5 MB | 2026-08-11 |

Refresh an introspection-based snapshot with:

```python
import httpx
from graphql import build_client_schema, get_introspection_query, print_schema

r = httpx.post(URL, json={"query": get_introspection_query()}, timeout=30)
print(print_schema(build_client_schema(r.json()["data"])))
```

and GitHub's directly: `curl -L https://docs.github.com/public/fpt/schema.docs.graphql`.

The nightly corpus-canary workflow runs the same generate-and-import
tests against the live endpoints (`pytest -m upstream`), so upstream
drift that breaks the emitters surfaces within a day even though these
snapshots stay frozen.
