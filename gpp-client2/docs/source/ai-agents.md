# Working with AI agents

This client ships with tools to make AI agents better at using it:
agent skills - one for the client itself and one for
[gqlforge](https://gqlforge.readthedocs.io), the
codegen it is built with (at `.claude/skills/gqlforge/SKILL.md`).

## The bundled skill

The repository contains a skill at `.claude/skills/gpp-client2/SKILL.md`. A
skill is a compact instruction file that coding agents such as Claude Code
load when relevant; this one teaches the agent the whole public surface of
gpp-client2: how to construct clients, every domain and method, the `UNSET`
semantics, the environment model, and a list of hard-won gotchas, each of
which was observed against a real deployment and has a regression test.

If you work inside this repository with Claude Code, the skill loads on its
own. To get the same effect in your own project, copy the skill directory
into your project:

```bash
mkdir -p .claude/skills
cp -r path/to/gpp-client2/.claude/skills/gpp-client2 .claude/skills/
```

From then on, asking your agent to "fetch the READY observations for
program p-123" produces code that handles `UNSET`, partial responses, and
environment differences correctly, because the skill tells it about all
three.

## Why the skill stays accurate

Documentation like this drifts unless something stops it. Here something
does: `tests/test_skill_doc.py` fails the build whenever a public method,
client attribute, or error type exists that the skill does not mention. The
skill is updated in the same commit as any API change, or the change does
not merge.

## The gotcha list

The skill's most useful section for humans is its gotchas: truthiness
conflating `UNSET`, `None`, and empty strings; fresh observations with
null calculated fields; soft deletes that look like data loss; bulk-shaped
results from by-id updates; and the rest. If you are debugging something
surprising, reading `.claude/skills/gpp-client2/SKILL.md` directly is a
fast way to find out whether the surprise is a known one.
