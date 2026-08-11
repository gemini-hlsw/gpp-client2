# Domains

You never pass a domain list anywhere - **creating a directory declares
a domain**, and everything downstream is derived.

## From folder to client attribute

1. **Declare.** Make `operations/<domain>/` (a snake_case identifier)
   and put `.graphql` files in it. The directory name is the domain
   key. `_`-prefixed directories (`_shared/`) hold fragments and never
   become domains.
2. **`gqlforge` maps.** Every operation in the directory is tagged with
   that domain. The folder name is pascal-cased and two classes are
   emitted into `<generated_package>.domains`:

   ```text
   operations/program/          class ProgramOperations:
     queries.graphql       ->       def __init__(self, executor: SyncExecutor)
     mutations.graphql          class AsyncProgramOperations:
                                    def __init__(self, executor: AsyncExecutor)
   ```

   Each operation becomes one method on both classes, its name derived
   from the operation name relative to the domain: `getProgramById` ->
   `get_by_id`, `getPrograms` -> `get_all`, `createProgram` ->
   `create`, `getSchedulerPrograms` in `scheduler/` -> `get_programs`.
   The classes need nothing but an executor - how you expose them is up
   to you.
3. **You structure.** The recommended pattern (gpp-client2's, enforced
   there by a conformance test) is one subclass per domain plus one
   registry:

   ```python
   # domains/program.py - inherit full coverage, add curated helpers
   class ProgramAPI(ProgramOperations):
       def get_all_active(self):  # curated logic lives here
           ...


   # domains/__init__.py - folder key -> (attribute, sync, async)
   DOMAIN_REGISTRY = {
       "program": ("programs", ProgramAPI, AsyncProgramAPI),
   }

   # client constructor
   for attribute, sync_cls, _ in DOMAIN_REGISTRY.values():
       setattr(self, attribute, sync_cls(executor))
   ```

   The registry is the one place a human names things: the folder
   `program` becomes the attribute `client.programs`. In vendored-runtime
   mode a default `Client`/`AsyncClient` is emitted with one attribute
   per folder name; the registry pattern is for when you want your own
   names and curated helpers instead. It also pays for
   itself downstream - `gpp-client2` derives its entire CLI and its
   per-domain reference docs by reflecting over the same registry.

`gqlforge scaffold <domain>` automates step 3: it creates the
operations directory and the subclass module, then prints the remaining
wiring.

## Don't want domains?

Both structures are optional:

- **No domains**: put `.graphql` files directly at the operations-tree
  root. They form one anonymous domain emitted as plain `Operations` /
  `AsyncOperations` classes, and with no domain to strip, method names
  keep their resource (`getWidgetById` -> `get_widget_by_id`). Your
  whole client can be `Operations(executor)`.
- **No operations at all**: with no operations tree, `gqlforge` is a
  models-only generator - it emits the pydantic scalars, enums, inputs,
  and models from the merged schema and skips the operation pipeline.
- **One schema**: a single entry in `source_order` makes the merge and
  pruning no-ops; you get an ordinary single-schema codegen with the
  multi-schema machinery dormant until you commit a second SDL.

Mixing is fine too: root-level files and domain directories can
coexist, and a project can start flat and grow domains later - the
generated class names are the only thing that changes.
