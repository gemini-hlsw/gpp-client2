"""Sphinx configuration for the gqlforge documentation."""

from importlib import metadata

project = "gqlforge"
author = "NOIRLab"

try:
    release = metadata.version("gqlforge")
except metadata.PackageNotFoundError:
    release = "0.0.0"
version = ".".join(release.split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinxarg.ext",
]

myst_enable_extensions = ["colon_fence"]

html_theme = "furo"
html_title = "gqlforge"
html_theme_options = {
    "source_repository": "https://github.com/gemini-hlsw/gpp-client2/",
    "source_branch": "main",
    "source_directory": "gqlforge/docs/source/",
}

copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True
