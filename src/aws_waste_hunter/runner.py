"""Run checks; a failing check is recorded, never fatal and never hidden."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from aws_waste_hunter.accounts import Target
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


DEFAULT_CONCURRENCY = 8
MAX_CONCURRENCY = 16  # stay well inside AWS API rate limits


def _scan_one(
    target: Target,
    region: str,
    prices_for: Callable[[Any, str], PriceBook],
    checks: list[Check] | None,
) -> ScanResult:
    session = target.session_factory()  # one session per task: boto3 sessions aren't thread-safe
    result = run_scan(session, region, checks, prices_for(session, region))
    acct = target.account_id
    result.account_id = acct
    result.findings = [dataclasses.replace(f, account_id=acct) for f in result.findings]
    result.errors = [dataclasses.replace(e, account_id=acct) for e in result.errors]
    return result


def run_multi(
    targets: list[Target],
    prices_for: Callable[[Any, str], PriceBook],
    checks: list[Check] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> ScanSummary:
    """Scan every (account, region) pair in parallel. Result order is deterministic."""
    workers = max(1, min(concurrency, MAX_CONCURRENCY))
    jobs = [(t, region) for t in targets for region in t.regions]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda j: _scan_one(j[0], j[1], prices_for, checks), jobs))
    return ScanSummary(results=results)
