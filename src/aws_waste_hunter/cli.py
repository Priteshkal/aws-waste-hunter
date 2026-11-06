"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aws_waste_hunter import __version__, report
from aws_waste_hunter.pricing import load_prices
from aws_waste_hunter.readonly import make_session
from aws_waste_hunter.regions import parse_region_list, validate_region
from aws_waste_hunter.runner import enabled_regions, run_multi


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aws-waste-hunter", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Scan for waste (read-only)")
    where = scan.add_mutually_exclusive_group(required=True)
    where.add_argument("--region", help="Scan one region, e.g. us-east-1")
    where.add_argument("--regions", help="Comma-separated regions, e.g. us-east-1,eu-west-1")
    where.add_argument("--all-regions", action="store_true", help="Scan every enabled region")
    scan.add_argument("--profile", help="AWS profile / SSO profile name")
    scan.add_argument("--format", choices=["json", "md"], default="md")
    scan.add_argument("--output", type=Path, help="Write report to a private (0600) file")
    scan.add_argument(
        "--pricing",
        choices=["live", "offline"],
        default="live",
        help="live: AWS Price List API with cache and offline fallback (default)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    session_kwargs = {"profile_name": args.profile} if args.profile else {}
    session = make_session(**session_kwargs)
    try:
        if args.all_regions:
            regions = enabled_regions(session)
        elif args.regions:
            regions = parse_region_list(args.regions)
        else:
            regions = [validate_region(args.region)]
    except ValueError as exc:
        parser.error(str(exc))
    summary = run_multi(session, regions, lambda r: load_prices(session, r, args.pricing))
    text = report.to_json(summary) if args.format == "json" else report.to_markdown(summary)
    if args.output:
        report.write_private(args.output, text)
    else:
        sys.stdout.write(text + "\n")
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
