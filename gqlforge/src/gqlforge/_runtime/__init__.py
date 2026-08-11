"""
Runtime templates vendored into generated packages.

Nothing in gqlforge imports these modules; ``gqlforge generate`` copies
them into the output package when no ``runtime_package`` is configured,
so generated code never depends on gqlforge at runtime. They use
relative imports throughout, which is what makes them location-agnostic.
"""

from pathlib import Path

RUNTIME_DIR = Path(__file__).parent

BASE_MODULES = ("_exceptions.py", "_base.py")
"""Vendored always - generated models need the bases and sentinel."""

CLIENT_MODULES = ("_executor.py", "_ws.py")
"""Vendored only when an operations tree exists."""
