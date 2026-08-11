"""
Sphinx configuration for the gpp-client2 documentation.

The CLI reference pages under ``cli/`` are written by this file at build
time, one per domain, straight from the client's own registry - nothing
under that directory is committed or edited by hand.
"""

import inspect
from importlib import metadata
from pathlib import Path

project = "gpp-client2"
author = "NOIRLab"
copyright = "%Y, NOIRLab"

try:
    release = metadata.version("gpp-client2")
except metadata.PackageNotFoundError:
    release = "0.0.0"
version = ".".join(release.split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinxcontrib.typer",
    "sphinx_copybutton",
]

myst_enable_extensions = ["colon_fence", "deflist"]

autodoc_member_order = "groupwise"
autodoc_typehints = "signature"
napoleon_google_docstring = False
napoleon_numpy_docstring = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = []
exclude_patterns = []

html_theme = "furo"
html_title = "gpp-client2"
html_theme_options = {
    "sidebar_hide_name": False,
}

copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True


# -- Generated CLI reference pages -------------------------------------------


def _generate_cli_pages() -> None:
    """
    Write one reference page per CLI command group, from the CLI itself.

    Each page's summary comes from the domain class docstring and its
    command reference from a ``typer`` directive, so adding a domain adds
    a finished docs page with no hand-written file.
    """
    from gpp_client2.domains import DOMAIN_REGISTRY

    cli_dir = Path(__file__).parent / "cli"
    cli_dir.mkdir(exist_ok=True)

    groups = []
    for attribute, sync_cls, _ in DOMAIN_REGISTRY.values():
        group = attribute.replace("_", "-")
        groups.append(group)
        doc = inspect.getdoc(sync_cls) or ""
        summary = next(
            (line.strip() for line in doc.splitlines() if line.strip()),
            f"{group} operations.",
        )
        title = f"gpp2 {group}"
        (cli_dir / f"{group}.rst").write_text(
            f"""{title}
{"=" * len(title)}

{summary} The Python equivalent is ``client.{attribute}``
(:doc:`../api`).

.. typer:: gpp_client2.cli.app:{group}
   :prog: gpp2 {group}
   :show-nested:
   :make-sections:
   :width: 80
""",
            encoding="utf-8",
        )

    toctree_entries = "\n".join(f"   {group}" for group in groups)
    index_title = "CLI reference"
    (cli_dir / "index.rst").write_text(
        f"""{index_title}
{"=" * len(index_title)}

The command tree, rendered from the CLI itself; every page below is
generated at build time from the client's domain registry, so this
reference always matches the installed version. Usage patterns and
examples are in :doc:`../cli`.

.. typer:: gpp_client2.cli.app
   :prog: gpp2
   :make-sections:
   :width: 80

.. toctree::
   :maxdepth: 1

{toctree_entries}
""",
        encoding="utf-8",
    )


_generate_cli_pages()


# -- Autodoc output cleanup ---------------------------------------------------


def _skip_model_config(app, what, name, obj, skip, options):
    """Hide pydantic ``model_config`` attributes everywhere."""
    if name == "model_config":
        return True
    return None


def setup(app):
    app.connect("autodoc-skip-member", _skip_model_config)
