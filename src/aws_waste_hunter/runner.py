"""Run checks; a failing check is recorded, never fatal and never hidden."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from aws_waste_hunter.checks import all_checks
from aws_waste_hunter.checks.base import Check
from aws_waste_hunter.models import CheckError, ScanResult, ScanSummary
from aws_waste_hunter.pricing import PriceBook
from aws_waste_hunter.readonly import client
from aws_waste_hunter.regions import validate_region


def run_scan(
    session: Any,
    region: str,
    checks: list[Check] | None = None,
    prices: PriceBook | None = None,
) -> ScanResult:
    prices = prices or PriceBook()
    result = ScanResult(region=region, pricing_source=prices.source)
    for check in checks if checks is not None else all_checks():
        try:
            result.findings.extend(check.run(session, region, prices))
        except (ClientError, BotoCoreError) as exc:
            result.errors.append(CheckError(check.id, region, str(exc)))
    result.findings.sort(key=lambda f: f.estimated_savings_usd or 0.0, reverse=True)
    return result


def enabled_regions(session: Any) -> list[str]:
    """Regions enabled for the account (opt-in regions that are off are excluded)."""
    ec2 = client(session, "ec2", "us-east-1")
    names = [r["RegionName"] for r in ec2.describe_regions(AllRegions=False)["Regions"]]
    return sorted(validate_region(n) for n in names)


def run_multi(
    session: Any,
    regions: list[str],
    prices_for: Callable[[str], PriceBook],
    checks: list[Check] | None = None,
) -> ScanSummary:
    summary = ScanSummary()
    for region in regions:
        summary.results.append(run_scan(session, region, checks, prices_for(region)))
    return summary
