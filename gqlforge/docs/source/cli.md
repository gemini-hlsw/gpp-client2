# CLI reference

Generated from the parser itself, so it cannot drift from the installed
version. Every command reads `[tool.gqlforge]` from the pyproject.toml
in the current directory.

```{eval-rst}
.. argparse::
   :module: gqlforge.__main__
   :func: build_parser
   :prog: gqlforge
```
