"""NAT gateways that moved no data for a week still cost about $33/month."""

from __future__ import annotations

from typing import Any, ClassVar

from aws_waste_hunter.metrics import (
    LOOKBACK_DAYS,
    MetricBudget,
    MetricBudgetExceeded,
    lookback_start,
    sum_metrics,
)
from aws_waste_hunter.models import Finding
from aws_waste_hunter.pricing import HOURS_PER_MONTH, PriceBook
from aws_waste_hunter.readonly import client

_METRICS = ("BytesOutToDestination", "BytesInFromSource")


class IdleNatGateways:
    id: ClassVar[str] = "nat-idle"
    required_actions: ClassVar[tuple[str, ...]] = (
        "ec2:DescribeNatGateways",
        "cloudwatch:GetMetricData",
    )

    def run(
        self,
        session: Any,
        region: str,
        prices: PriceBook,
        budget: MetricBudget | None = None,
    ) -> list[Finding]:
        budget = budget or MetricBudget()
        ec2 = client(session, "ec2", region)
        cutoff = lookback_start()
        nats = [
            n
            for page in ec2.get_paginator("describe_nat_gateways").paginate()
            for n in page["NatGateways"]
            # Only judge gateways that existed for the whole window.
            if n["State"] == "available" and n["CreateTime"] <= cutoff
        ]
        findings: list[Finding] = []
        cost = round(prices.nat_gateway_hourly * HOURS_PER_MONTH, 2)
        for nat in nats:
            queries = {
                m: ("AWS/NATGateway", m, [{"Name": "NatGatewayId", "Value": nat["NatGatewayId"]}])
                for m in _METRICS
            }
            try:
                totals = sum_metrics(session, region, budget, queries)
            except MetricBudgetExceeded as exc:
                raise MetricBudgetExceeded(str(exc), findings) from exc
            if sum(totals.values()) == 0:
                findings.append(
                    Finding(
                        check_id=self.id,
                        resource_id=nat["NatGatewayId"],
                        region=region,
                        reason=f"NAT gateway moved 0 bytes in the last {LOOKBACK_DAYS} days",
                        recommendation=(
                            "Confirm nothing routes through it (check route tables), "
                            "then delete it."
                        ),
                        monthly_cost_usd=cost,
                        estimated_savings_usd=cost,
                        confidence="medium",
                    )
                )
        return findings
