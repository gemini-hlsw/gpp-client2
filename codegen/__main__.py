"""
Command-line entry point: ``python -m codegen <subcommand>``.
"""

import argparse
import sys

from codegen import CodegenError
from codegen.pipeline import run_check, run_download, run_generate, run_readiness


def main() -> int:
    parser = argparse.ArgumentParser(prog="codegen", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser(
        "download", help="Download the GraphQL schema for one or all environments."
    )
    download.add_argument(
        "source",
        nargs="?",
        help="Environment to download (development, staging, production). "
        "Downloads all configured environments when omitted.",
    )
    subparsers.add_parser(
        "generate",
        help="Merge schemas, emit models and domains, and derive per-"
        "environment operation text.",
    )
    subparsers.add_parser(
        "check", help="Run generate and fail if any committed artifact changed."
    )
    subparsers.add_parser("readiness", help="Print the promotion-readiness report.")
    scaffold = subparsers.add_parser(
        "scaffold", help="Create the skeleton for a new domain."
    )
    scaffold.add_argument("domain", help="Domain name, e.g. call_for_proposals.")

    args = parser.parse_args()
    try:
        if args.command == "download":
            run_download(args.source)
        elif args.command == "generate":
            run_generate()
        elif args.command == "check":
            run_check()
        elif args.command == "readiness":
            return run_readiness()
        elif args.command == "scaffold":
            from codegen.scaffold import run_scaffold

            run_scaffold(args.domain)
    except CodegenError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
