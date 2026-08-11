"""
Consumer configuration: the ``[tool.gqlforge]`` table in pyproject.toml.

gqlforge is driven entirely by the consuming project's pyproject. Paths are
resolved relative to the pyproject's directory, so ``gqlforge <command>``
works from the project root with no arguments.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from gqlforge import GqlforgeError

__all__ = ["Config"]

_REQUIRED = (
    "schemas",
    "operations",
    "output",
    "merged_schema",
    "availability",
    "source_order",
    "generated_package",
)


@dataclass(frozen=True)
class Config:
    """
    Resolved gqlforge settings for one consuming project.

    Parameters
    ----------
    root : Path
        Directory containing the pyproject.toml; all paths resolve
        against it.
    schemas_dir : Path
        Directory holding one ``<source>.graphql`` SDL file per schema
        source.
    operations_dir : Path
        The union operations tree; each subdirectory is a domain,
        ``_``-prefixed directories hold shared fragments.
    generated_dir : Path
        Output directory for the generated modules.
    merged_schema_path : Path
        Where the merged (union) schema SDL is written.
    availability_path : Path
        Where the availability manifest JSON is written.
    source_order : tuple[str, ...]
        Schema sources ordered newest first; a source participates only
        when its SDL file exists.
    generated_package : str
        Dotted import path of the generated package, used in emitted
        cross-module imports (e.g. ``myclient._generated``).
    runtime_package : str
        Package exposing the runtime contract the generated code imports:
        ``<runtime_package>._base`` must provide the model bases and the
        ``UNSET`` sentinel, ``<runtime_package>._executor`` the
        ``SyncExecutor`` and ``AsyncExecutor`` protocols. When the key is
        omitted, gqlforge vendors its own runtime into the generated
        package and this resolves to ``generated_package``.
    vendor_runtime : bool
        True when no ``runtime_package`` was configured: the runtime
        modules and a default client are emitted alongside the models.
    model_base : str
        Class name in ``<runtime_package>._base`` that output models
        inherit.
    input_base : str
        Class name in ``<runtime_package>._base`` that input models
        inherit.
    domains_dir : Path | None
        Where ``gqlforge scaffold`` writes hand-written domain modules.
    environments : str | None
        ``module:attribute`` import string for the download registry - an
        iterable of objects with ``name`` and ``base_url`` attributes.
    download_token : str | None
        Optional ``module:attribute`` import string for a callable
        ``(source_name) -> str | None`` that supplies a download token.
    token_env : str | None
        Environment variable consulted for a download token when the
        ``download_token`` hook is absent or returns ``None``.
    """

    root: Path
    schemas_dir: Path
    operations_dir: Path
    generated_dir: Path
    merged_schema_path: Path
    availability_path: Path
    source_order: tuple[str, ...]
    generated_package: str
    runtime_package: str
    vendor_runtime: bool
    model_base: str
    input_base: str
    domains_dir: Path | None
    environments: str | None
    download_token: str | None
    token_env: str | None

    @classmethod
    def load(cls, root: Path | None = None) -> Config:
        """Read ``[tool.gqlforge]`` from ``<root>/pyproject.toml``."""
        root = (root or Path.cwd()).resolve()
        pyproject = root / "pyproject.toml"
        if not pyproject.is_file():
            raise GqlforgeError(f"No pyproject.toml found in {root}.")
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        table: dict[str, Any] = data.get("tool", {}).get("gqlforge", {})
        if not table:
            raise GqlforgeError(f"No [tool.gqlforge] table in {pyproject}.")
        missing = [key for key in _REQUIRED if key not in table]
        if missing:
            raise GqlforgeError(
                f"[tool.gqlforge] is missing required keys: {', '.join(missing)}."
            )
        runtime_package = table.get("runtime_package")
        return cls(
            root=root,
            schemas_dir=root / table["schemas"],
            operations_dir=root / table["operations"],
            generated_dir=root / table["output"],
            merged_schema_path=root / table["merged_schema"],
            availability_path=root / table["availability"],
            source_order=tuple(table["source_order"]),
            generated_package=table["generated_package"],
            # Absent runtime_package -> gqlforge vendors the runtime into
            # the generated package, so the emitted imports point there.
            runtime_package=runtime_package or table["generated_package"],
            vendor_runtime=runtime_package is None,
            model_base=table.get("model_base", "Model"),
            input_base=table.get("input_base", "Input"),
            domains_dir=(
                root / table["domains_dir"] if "domains_dir" in table else None
            ),
            environments=table.get("environments"),
            download_token=table.get("download_token"),
            token_env=table.get("token_env"),
        )


def import_hook(spec: str) -> Any:
    """Resolve a ``module:attribute`` import string."""
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise GqlforgeError(
            f"Invalid import string '{spec}'; expected 'module:attribute'."
        )
    try:
        return getattr(import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise GqlforgeError(f"Could not import '{spec}': {exc}") from exc
