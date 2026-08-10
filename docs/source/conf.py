"""Sphinx configuration for the gpp-client2 documentation."""

from importlib import metadata

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
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
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
