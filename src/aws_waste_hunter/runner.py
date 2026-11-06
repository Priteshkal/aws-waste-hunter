"""Run checks; a failing check is recorded, never fatal and never hidden."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from aws_waste_hunter.checks import all_checks
from aws_waste_hunter.checks.base import Check
from aws_waste_hunter.models import CheckError, ScanResult
from aws_waste_hunter.pricing import PriceBook


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
