"""Shared helper: build a minimal consumer project for generation tests.

The consumer gets a real (tiny) runtime package satisfying the contract
generated code imports - ``<package>._base`` with the ``UNSET`` sentinel
and base classes, ``<package>._executor`` with the executor names - so
tests can import and instantiate what gqlforge emits, not just diff it.
"""

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path

from gqlforge.config import Config

_PYPROJECT = """\
[tool.gqlforge]
schemas = "schemas"
operations = "operations"
output = "{package}/_generated"
merged_schema = "merged.graphql"
availability = "availability.json"
source_order = [{sources}]
generated_package = "{package}._generated"
runtime_package = "{package}"
"""

_RUNTIME_BASE = """\
from typing import Any

from pydantic import BaseModel


class UnsetType:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self):
        return False

    def __repr__(self):
        return "UNSET"


UNSET: Any = UnsetType()


class Model(BaseModel):
    model_config = {"populate_by_name": True}


class Input(BaseModel):
    model_config = {"populate_by_name": True}
"""

_RUNTIME_EXECUTOR = """\
class SyncExecutor:
    pass


class AsyncExecutor:
    pass
"""


def make_consumer(
    root: Path,
    package: str,
    schemas: dict[str, str],
    source_order: list[str],
    operations: str | None = None,
) -> Config:
    """Write a complete consumer project under ``root`` and load its config."""
    sources = ", ".join(f'"{s}"' for s in source_order)
    (root / "pyproject.toml").write_text(
        _PYPROJECT.format(package=package, sources=sources), encoding="utf-8"
    )
    (root / "schemas").mkdir()
    for source, sdl in schemas.items():
        (root / "schemas" / f"{source}.graphql").write_text(sdl, encoding="utf-8")
    if operations is not None:
        (root / "operations").mkdir()
        (root / "operations" / "queries.graphql").write_text(
            operations, encoding="utf-8"
        )
    package_dir = root / package
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "_base.py").write_text(_RUNTIME_BASE, encoding="utf-8")
    (package_dir / "_executor.py").write_text(_RUNTIME_EXECUTOR, encoding="utf-8")
    return Config.load(root)


@contextmanager
def importable(root: Path, package: str):
    """Make the consumer importable; purge it from sys.modules afterwards."""
    sys.path.insert(0, str(root))
    try:
        yield lambda module: importlib.import_module(f"{package}.{module}")
    finally:
        sys.path.remove(str(root))
        for name in [m for m in sys.modules if m.split(".")[0] == package]:
            del sys.modules[name]
