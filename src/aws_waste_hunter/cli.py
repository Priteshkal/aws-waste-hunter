"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aws_waste_hunter import __version__, report
from aws_waste_hunter.readonly import make_session
from aws_waste_hunter.runner import run_scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aws-waste-hunter", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Scan one region for waste (read-only)")
    scan.add_argument("--region", required=True)
    scan.add_argument("--profile", help="AWS profile / SSO profile name")
    scan.add_argument("--format", choices=["json", "md"], default="md")
    scan.add_argument("--output", type=Path, help="Write report to a file instead of stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_kwargs = {"profile_name": args.profile} if args.profile else {}
    session = make_session(**session_kwargs)
    result = run_scan(session, args.region)
    text = report.to_json(result) if args.format == "json" else report.to_markdown(result)
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text + "\n")
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
