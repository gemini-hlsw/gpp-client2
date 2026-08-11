"""
gqlforge: multi-schema GraphQL-to-Python code generation.

One union operations tree, validated against the merge of every schema
source, pruned per source, and emitted as pydantic models plus sync and
async client bases. Configuration lives in the consuming project's
``[tool.gqlforge]`` pyproject table; run ``gqlforge <subcommand>`` from the
project root.
"""

__all__ = ["GqlforgeError"]


class GqlforgeError(RuntimeError):
    """Raised when any gqlforge step fails."""
