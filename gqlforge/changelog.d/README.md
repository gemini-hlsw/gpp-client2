# Changelog fragments

Every change worth telling gqlforge users about gets one file here,
written when the change is made, not at release time. Towncrier compiles
them into `CHANGELOG.md` at release and deletes them.

File name: `<issue>.<type>.md` with a GitHub issue, or
`+<slug>.<type>.md` without (the `+` marks an issue-less fragment).

Types mirror Conventional Commits: `feat`, `fix`, `perf`, `docs`,
`removal`, `misc`.

Content: one short sentence in Markdown, written for a user of the
library, ending with a period.

```bash
cd gqlforge
uv run towncrier build --draft        # preview the compiled changelog
uv run towncrier build --version X.Y.Z   # at release
```
