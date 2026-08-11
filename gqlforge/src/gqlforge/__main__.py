"""
Command-line entry point: ``gqlforge <subcommand>``.
"""

import argparse
import sys
from pathlib import Path

from gqlforge import GqlforgeError
from gqlforge.config import Config
from gqlforge.pipeline import run_check, run_download, run_generate, run_readiness


def build_parser() -> argparse.ArgumentParser:
    """The gqlforge argument parser (also used by the docs to self-document)."""
    parser = argparse.ArgumentParser(
        prog="gqlforge",
        description="Run from the consuming project's root - the directory "
        "whose pyproject.toml holds the [tool.gqlforge] table.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "generate",
        help="Merge schemas, validate and prune the operations tree, and "
        "emit models, the operation map, and domain classes.",
    )
    subparsers.add_parser(
        "check",
        help="Run generate and fail if any committed artifact changed (use in CI).",
    )
    subparsers.add_parser(
        "readiness",
        help="Report what the newest schema source has that the oldest "
        "lacks, and whether anything blocks promotion.",
    )
    download = subparsers.add_parser(
        "download",
        help="Refresh committed schema SDL via a live introspection request.",
    )
    download.add_argument(
        "source",
        nargs="?",
        help="Schema source to download; every configured source when omitted.",
    )
    scaffold = subparsers.add_parser(
        "scaffold", help="Create the skeleton for a new domain."
    )
    scaffold.add_argument("domain", help="Domain name, e.g. call_for_proposals.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = Config.load(Path.cwd())
        if args.command == "download":
            run_download(config, args.source)
        elif args.command == "generate":
            run_generate(config)
        elif args.command == "check":
            run_check(config)
        elif args.command == "readiness":
            return run_readiness(config)
        elif args.command == "scaffold":
            from gqlforge.scaffold import run_scaffold

            run_scaffold(config, args.domain)
    except GqlforgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
