"""Sphinx configuration for the gqlforge documentation.

The showcase artifacts under ``_showcase/gen/`` are written by this file
at build time by running the real pipeline over the committed Rick and
Morty corpus snapshot - nothing under that directory is committed or
edited by hand, so the showcase page can never drift from the emitters.
"""

import contextlib
import io
from importlib import metadata
from pathlib import Path

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
    "sphinxcontrib.typer",
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


# -- Generated showcase artifacts ---------------------------------------------


def _generate_showcase() -> None:
    """
    Run the pipeline over the Rick and Morty corpus snapshot.

    The showcase page literalincludes the emitted files and the console
    transcript from ``_showcase/gen/``, so what readers see is what the
    installed emitters actually produce.
    """
    from gqlforge.config import Config
    from gqlforge.pipeline import run_generate

    demo = Path(__file__).parent / "_showcase"
    gen = demo / "gen"
    gen.mkdir(exist_ok=True)
    config = Config(
        root=demo,
        schemas_dir=Path(__file__).parents[2] / "tests" / "schemas",
        operations_dir=demo / "operations",
        generated_dir=gen / "_generated",
        merged_schema_path=gen / "merged.graphql",
        availability_path=gen / "availability.json",
        source_order=("rickandmorty",),
        generated_package="ram._generated",
        runtime_package="ram._generated",
        vendor_runtime=True,
        model_base="Model",
        input_base="Input",
        domains_dir=None,
        environments=None,
        download_token=None,
        token_env=None,
    )
    transcript = io.StringIO()
    with contextlib.redirect_stdout(transcript):
        run_generate(config)
    (gen / "generate.log").write_text(
        "$ gqlforge generate\n" + transcript.getvalue(), encoding="utf-8"
    )


_generate_showcase()
