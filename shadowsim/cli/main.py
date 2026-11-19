"""ShadowSim command-line entry point."""

import argparse
import json
import sys
from collections.abc import Callable

from shadowsim.cli.commands import add_research_parsers
from shadowsim.cli.serve import add_serve_parser


def build_parser() -> argparse.ArgumentParser:
    """Build the ``shadowsim`` argument parser."""
    parser = argparse.ArgumentParser(prog="shadowsim", description="ShadowSim commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_serve_parser(subparsers)
    add_research_parsers(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ``shadowsim`` command-line interface."""
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.handler
    try:
        return handler(args)
    except (ValueError, ImportError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
