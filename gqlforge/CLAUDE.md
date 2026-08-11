# gqlforge

Multi-schema GraphQL-to-Python codegen: one union operations tree,
merged-schema validation, per-schema pruning, pydantic models with the
`UNSET` sentinel, sync+async client bases from one spec. Driven by a
`[tool.gqlforge]` table in the consuming project's pyproject.toml.
Repo-wide rules live in the root CLAUDE.md; run the commands below from
this directory.

## Commands

```bash
uv run pytest                            # unit + end-to-end suite
uv run sphinx-build -W docs/source docs/_build   # the documentation
uv run towncrier build --draft           # preview the changelog
```

The CLI itself (`gqlforge generate|check|readiness|download|scaffold`)
runs from a *consumer's* root - exercise it against gpp-client2 by
running it from `../gpp-client2/`.

## Hard rules

- **The reference consumer must stay green.** Any emitter or pipeline
  change requires `cd ../gpp-client2 && uv run gqlforge check && uv run
  pytest`. An intentional output change shows up there as a generated
  diff - regenerate and commit it with the change; an unintentional one
  is a bug.
- A selection that survives in **no** schema source is a build error,
  never a warning; every pruned document must re-validate against its
  own schema before emission.
- Never prune `__typename`-only selection sets; authors probe types
  that way.
- Config keys and CLI subcommands are documented in the agent skill
  (`.claude/skills/gqlforge/SKILL.md` at the repo root);
  `tests/test_skill_doc.py` fails when they drift. Update the skill in
  the same change.
- Generated-code contracts that exist for consumers' sake: aliases use
  `validation_alias`/`serialization_alias` (never `alias=`), emitted
  imports come from the consumer's `runtime_package` (or the vendored
  copy inside the generated package), and gqlforge itself must never
  become a runtime dependency of generated code - the runtime is
  VENDORED (copied from `src/gqlforge/_runtime/`), never imported.
- The vendored runtime templates in `src/gqlforge/_runtime/` are real
  lintable modules with relative imports; nothing in gqlforge imports
  them, and `tests/test_runtime.py` exercises the emitted copies end to
  end over httpx.MockTransport - including the unit contracts for the
  model bases and executor core (moved here from gpp-client2 when it
  adopted the vendored runtime; this suite is their only home).
- gpp-client2 runs ON the vendored runtime: its `_base.py`/
  `_executor.py`/`_ws.py` are shims re-exporting `_generated.*` and its
  clients subclass the emitted `client.py` (via `executor_core_class`
  and `_wire_domains()`). A runtime bug fixed here reaches it by
  regeneration - there is no second copy to keep in sync anymore.
- The end-to-end test (`tests/test_endtoend.py`) generates a complete
  minimal consumer; new pipeline features get their coverage there, not
  only in unit tests.
- The corpus suite (`tests/test_corpus.py`) generates from committed
  snapshots of real public schemas (`tests/schemas/`, provenance in its
  README) and imports the results; emitter changes must keep the whole
  corpus importable. The GitHub schema makes it take ~20s - that is the
  point, not a problem. The same tests also run nightly against the
  *live* upstream APIs (`pytest -m upstream`, corpus_canary.yaml) to
  catch new real-world schema shapes early; fetch failures skip,
  generation failures fail.

## Layout

`src/gqlforge/`: `config.py` (the `[tool.gqlforge]` loader),
`schema.py` (merge), `operations.py` (tree loading, `__typename`
injection, comment-docstring capture), `prune.py` (per-schema pruning),
`emit_models.py` / `emit_operations.py` (emitters), `naming.py`
(operation-name -> method-name convention), `_runtime/` (vendored
runtime templates), `pipeline.py`
(generate/check/readiness/download), `scaffold.py`, `__main__.py`.
`docs/` is the Sphinx site (RTD subproject of gpp-client2).
