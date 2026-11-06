"""CloudWatch log groups that never expire keep growing the storage bill forever."""

from __future__ import annotations

from typing import Any, ClassVar

from aws_waste_hunter.metrics import MetricBudget
from aws_waste_hunter.models import Finding
from aws_waste_hunter.pricing import PriceBook
from aws_waste_hunter.readonly import client

_GIB = 1024**3


class LogGroupsWithoutRetention:
    id: ClassVar[str] = "logs-no-retention"
    required_actions: ClassVar[tuple[str, ...]] = ("logs:DescribeLogGroups",)

    def run(
        self,
        session: Any,
        region: str,
        prices: PriceBook,
        budget: MetricBudget | None = None,
    ) -> list[Finding]:
        logs = client(session, "logs", region)
        findings: list[Finding] = []
        for page in logs.get_paginator("describe_log_groups").paginate():
            for group in page["logGroups"]:
                if "retentionInDays" in group:
                    continue
                gib = group.get("storedBytes", 0) / _GIB
                findings.append(
                    Finding(
                        check_id=self.id,
                        resource_id=group["logGroupName"],
                        region=region,
                        reason=f"Log group never expires ({gib:.2f} GiB stored)",
                        recommendation=(
                            "Set a retention policy (for example 30-90 days) or export to S3. "
                            "Savings depend on how much data is older than the new retention."
                        ),
                        monthly_cost_usd=round(gib * prices.logs_storage_gb_month, 2),
                        estimated_savings_usd=None,
                        confidence="low",
                    )
                )
        return findings
