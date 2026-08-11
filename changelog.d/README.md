# Changelog fragments

Every change worth telling users about gets one file in this directory,
written when the change is made, not at release time. Towncrier compiles
them into `CHANGELOG.md` at release and deletes them.

File name: `<issue>.<type>.md` when there is a GitHub issue, or
`+<slug>.<type>.md` when there is not (the `+` marks an issue-less
fragment; the slug just keeps names unique).

Types mirror Conventional Commits: `feat`, `fix`, `perf`, `docs`,
`removal`, `misc`.

Content: one short sentence in Markdown, written for a user of the
library, ending with a period.

```bash
echo "Add the site_status domain." > changelog.d/+site-status.feat.md
uv run towncrier build --draft        # preview the compiled changelog
```
