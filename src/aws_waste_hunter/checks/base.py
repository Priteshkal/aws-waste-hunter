"""Check interface."""

from __future__ import annotations

from typing import Any, ClassVar, Protocol

from aws_waste_hunter.metrics import MetricBudget
from aws_waste_hunter.models import Finding
from aws_waste_hunter.pricing import PriceBook


class Check(Protocol):
    id: ClassVar[str]
    # IAM actions this check needs; a test asserts they are all in iam/policy.json.
    required_actions: ClassVar[tuple[str, ...]]

    def run(
        self,
        session: Any,
        region: str,
        prices: PriceBook,
        budget: MetricBudget | None = None,
    ) -> list[Finding]: ...
