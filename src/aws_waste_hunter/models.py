"""Core data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class Finding:
    """One piece of potential waste."""

    check_id: str
    resource_id: str
    region: str
    reason: str
    recommendation: str
    monthly_cost_usd: float
    # None when savings cannot be estimated without more data (e.g. log retention).
    estimated_savings_usd: float | None
    confidence: Confidence
    account_id: str = ""


@dataclass(frozen=True)
class CheckError:
    """A check that could not complete (e.g. missing permission). Never silently dropped."""

    check_id: str
    region: str
    message: str
    account_id: str = ""


@dataclass
class ScanResult:
    region: str
    pricing_source: str
    account_id: str = ""
    findings: list[Finding] = field(default_factory=list)
    errors: list[CheckError] = field(default_factory=list)

    @property
    def total_savings_usd(self) -> float:
        return round(sum(f.estimated_savings_usd or 0.0 for f in self.findings), 2)


@dataclass
class ScanSummary:
    """Results of scanning one or more regions."""

    results: list[ScanResult] = field(default_factory=list)

    @property
    def regions(self) -> list[str]:
        return list(dict.fromkeys(r.region for r in self.results))

    @property
    def accounts(self) -> list[str]:
        return list(dict.fromkeys(r.account_id for r in self.results if r.account_id))

    @property
    def findings(self) -> list[Finding]:
        merged = [f for r in self.results for f in r.findings]
        return sorted(merged, key=lambda f: f.estimated_savings_usd or 0.0, reverse=True)

    @property
    def errors(self) -> list[CheckError]:
        return [e for r in self.results for e in r.errors]

    @property
    def total_savings_usd(self) -> float:
        return round(sum(r.total_savings_usd for r in self.results), 2)
