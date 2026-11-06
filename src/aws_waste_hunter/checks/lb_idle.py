"""Application/Network load balancers with no traffic for a week still bill hourly."""

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

# type -> (namespace, metric). ProcessedBytes counts all traffic (incl. fixed-response rules).
_TRAFFIC_METRIC = {
    "application": ("AWS/ApplicationELB", "ProcessedBytes"),
    "network": ("AWS/NetworkELB", "ProcessedBytes"),
}


def _dimension_value(arn: str) -> str:
    # arn:aws:elasticloadbalancing:region:acct:loadbalancer/app/name/id -> app/name/id
    return arn.split(":loadbalancer/", 1)[1]


class IdleLoadBalancers:
    id: ClassVar[str] = "lb-idle"
    required_actions: ClassVar[tuple[str, ...]] = (
        "elasticloadbalancing:DescribeLoadBalancers",
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
        elb = client(session, "elbv2", region)
        cutoff = lookback_start()
        lbs = [
            lb
            for page in elb.get_paginator("describe_load_balancers").paginate()
            for lb in page["LoadBalancers"]
            if lb.get("Type") in _TRAFFIC_METRIC
            and lb["State"]["Code"] == "active"
            and lb["CreatedTime"] <= cutoff
        ]
        findings: list[Finding] = []
        cost = round(prices.lb_hourly * HOURS_PER_MONTH, 2)
        for lb in lbs:
            ns, metric = _TRAFFIC_METRIC[lb["Type"]]
            dims = [{"Name": "LoadBalancer", "Value": _dimension_value(lb["LoadBalancerArn"])}]
            try:
                totals = sum_metrics(session, region, budget, {"t": (ns, metric, dims)})
            except MetricBudgetExceeded as exc:
                raise MetricBudgetExceeded(str(exc), findings) from exc
            if totals["t"] == 0:
                findings.append(
                    Finding(
                        check_id=self.id,
                        resource_id=lb["LoadBalancerName"],
                        region=region,
                        reason=(
                            f"{lb['Type']} load balancer received no traffic in the last "
                            f"{LOOKBACK_DAYS} days"
                        ),
                        recommendation=(
                            "Confirm it is not a standby or seasonal endpoint, then delete it."
                        ),
                        monthly_cost_usd=cost,
                        estimated_savings_usd=cost,
                        confidence="medium",
                    )
                )
        return findings
