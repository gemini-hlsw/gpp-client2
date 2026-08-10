"""
Code generation pipeline for the GPP client.

This package is a development tool; it is not shipped in the wheel. It turns
the committed environment schemas plus one union operations tree into
everything under ``src/gpp_client/_generated``.

Run it with ``uv run python -m codegen <subcommand>``.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "graphql" / "schemas"
OPERATIONS_DIR = REPO_ROOT / "graphql" / "operations"
AVAILABILITY_PATH = REPO_ROOT / "graphql" / "availability.json"
MERGED_SCHEMA_PATH = SCHEMAS_DIR / "merged.graphql"
GENERATED_DIR = REPO_ROOT / "src" / "gpp_client" / "_generated"

# Schema sources ordered by distance ahead of production, newest first.
# A source participates only when its .graphql file is committed.
SOURCE_ORDER = ("development", "staging", "production")


class CodegenError(RuntimeError):
    """Raised when any codegen step fails."""
