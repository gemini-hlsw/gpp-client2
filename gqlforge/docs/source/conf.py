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


# -- Generated CLI reference -------------------------------------------------


def _generate_cli_page() -> None:
    """
    Write cli.md from the argument parser itself, at build time.

    Rendering the parser here (instead of via sphinx-argparse) keeps the
    page drift-proof while staying safe under parallel Sphinx builds,
    which Read the Docs uses.
    """
    import argparse
    from pathlib import Path

    from gqlforge.__main__ import build_parser

    parser = build_parser()
    subparsers = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    helps = {a.dest: a.help for a in subparsers._choices_actions}

    lines = [
        "# CLI reference",
        "",
        "Generated from the argument parser at docs build time, so it",
        "cannot drift from the installed version. " + parser.description,
        "",
    ]
    for name, sub in subparsers.choices.items():
        lines.append(f"## gqlforge {name}")
        lines.append("")
        lines.append(helps[name])
        lines.append("")
        lines.append("```text")
        lines.append(sub.format_usage().rstrip())
        lines.append("```")
        arguments = [a for a in sub._actions if not isinstance(a, argparse._HelpAction)]
        if arguments:
            lines.append("")
            for action in arguments:
                lines.append(f"- `{action.dest}` - {action.help}")
        lines.append("")
    Path(__file__).parent.joinpath("cli.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


_generate_cli_page()
