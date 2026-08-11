"""
Command-line entry point: ``gqlforge <subcommand>``.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from gqlforge import GqlforgeError
from gqlforge.config import Config

app = typer.Typer(
    name="gqlforge",
    help="Multi-schema GraphQL-to-Python codegen. Run from the consuming "
    "project's root - the directory whose pyproject.toml holds the "
    "\\[tool.gqlforge] table.",
    no_args_is_help=True,
)


def _run(action: Callable[[Config], None]) -> None:
    """Load config from the current directory, run, translate errors."""
    try:
        action(Config.load(Path.cwd()))
    except GqlforgeError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def generate() -> None:
    """Merge schemas, validate and prune the operations tree, and emit
    models, the operation map, and domain classes."""
    from gqlforge.pipeline import run_generate

    _run(run_generate)


@app.command()
def check() -> None:
    """Run generate and fail if any committed artifact changed (use in CI)."""
    from gqlforge.pipeline import run_check

    _run(run_check)


@app.command()
def readiness() -> None:
    """Report what the newest schema source has that the oldest lacks, and
    whether anything blocks promotion."""
    from gqlforge.pipeline import run_readiness

    code = 0

    def action(config: Config) -> None:
        nonlocal code
        code = run_readiness(config)

    _run(action)
    if code:
        raise typer.Exit(code)


@app.command()
def download(
    source: Annotated[
        str | None,
        typer.Argument(
            help="Schema source to download; every configured source when omitted."
        ),
    ] = None,
) -> None:
    """Refresh committed schema SDL via a live introspection request."""
    from gqlforge.pipeline import run_download

    _run(lambda config: run_download(config, source))


@app.command()
def scaffold(
    domain: Annotated[
        str, typer.Argument(help="Domain name, e.g. call_for_proposals.")
    ],
) -> None:
    """Create the skeleton for a new domain."""
    from gqlforge.scaffold import run_scaffold

    _run(lambda config: run_scaffold(config, domain))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
