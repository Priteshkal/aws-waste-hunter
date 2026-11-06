"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from aws_waste_hunter import __version__, report
from aws_waste_hunter.accounts import (
    Target,
    account_id_of,
    assume_role_session_kwargs,
    session_factory,
    validate_external_id,
    validate_role_arn,
)
from aws_waste_hunter.pricing import load_prices
from aws_waste_hunter.readonly import make_session
from aws_waste_hunter.regions import parse_region_list, validate_region
from aws_waste_hunter.runner import DEFAULT_CONCURRENCY, MAX_CONCURRENCY, enabled_regions, run_multi


def _concurrency(value: str) -> int:
    n = int(value)
    if not 1 <= n <= MAX_CONCURRENCY:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_CONCURRENCY}")
    return n


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
    scan.add_argument(
        "--role-arn",
        action="append",
        help="Scan another account by assuming this read-only role (repeatable)",
    )
    scan.add_argument(
        "--external-id", help="ExternalId for the assumed role(s) (applied to every --role-arn)"
    )
    scan.add_argument("--format", choices=["json", "md"], default="md")
    scan.add_argument("--output", type=Path, help="Write report to a private (0600) file")
    scan.add_argument(
        "--pricing",
        choices=["live", "offline"],
        default="live",
        help="live: AWS Price List API with cache and offline fallback (default)",
    )
    scan.add_argument(
        "--concurrency",
        type=_concurrency,
        default=DEFAULT_CONCURRENCY,
        help=f"Parallel scans, 1-{MAX_CONCURRENCY} (default {DEFAULT_CONCURRENCY})",
    )
    return parser


def _build_targets(args: argparse.Namespace) -> list[Target]:
    # Validate user input before making any AWS call.
    static_regions: list[str] | None = None
    if args.regions is not None:
        static_regions = parse_region_list(args.regions)
    elif args.region is not None:
        static_regions = [validate_region(args.region)]
    for arn in args.role_arn or []:
        validate_role_arn(arn)
    if args.external_id:
        validate_external_id(args.external_id)

    base_kwargs: dict[str, Any] = {"profile_name": args.profile} if args.profile else {}
    base = make_session(**base_kwargs)

    def regions_for(session: Any) -> list[str]:
        return static_regions if static_regions is not None else enabled_regions(session)

    if not args.role_arn:
        return [Target(account_id_of(base), session_factory(**base_kwargs), regions_for(base))]
    targets = []
    for arn in dict.fromkeys(args.role_arn):
        factory = session_factory(**assume_role_session_kwargs(base, arn, args.external_id))
        session = factory()
        targets.append(Target(account_id_of(session), factory, regions_for(session)))
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.external_id and not args.role_arn:
        parser.error("--external-id requires --role-arn")
    try:
        targets = _build_targets(args)
    except ValueError as exc:
        parser.error(str(exc))
    except (ClientError, BotoCoreError) as exc:
        sys.stderr.write(f"error: could not set up scan: {exc}\n")
        return 2
    summary = run_multi(
        targets,
        lambda session, region: load_prices(session, region, args.pricing),
        concurrency=args.concurrency,
    )
    text = report.to_json(summary) if args.format == "json" else report.to_markdown(summary)
    if args.output:
        report.write_private(args.output, text)
    else:
        sys.stdout.write(text + "\n")
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
