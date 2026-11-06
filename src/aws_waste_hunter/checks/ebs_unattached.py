"""Unattached (status=available) EBS volumes: pure waste until deleted."""

from __future__ import annotations

from typing import Any, ClassVar

from aws_waste_hunter.models import Finding
from aws_waste_hunter.pricing import PriceBook


class UnattachedEbsVolumes:
    id: ClassVar[str] = "ebs-unattached"
    required_actions: ClassVar[tuple[str, ...]] = ("ec2:DescribeVolumes",)

    def run(self, session: Any, region: str, prices: PriceBook) -> list[Finding]:
        ec2 = session.client("ec2", region_name=region)
        findings: list[Finding] = []
        pages = ec2.get_paginator("describe_volumes").paginate(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )
        for page in pages:
            for vol in page["Volumes"]:
                cost = round(vol["Size"] * prices.ebs_gb_month(vol["VolumeType"]), 2)
                findings.append(
                    Finding(
                        check_id=self.id,
                        resource_id=vol["VolumeId"],
                        region=region,
                        reason=f"{vol['Size']} GiB {vol['VolumeType']} volume is not attached",
                        recommendation="Snapshot if needed, then delete the volume.",
                        monthly_cost_usd=cost,
                        estimated_savings_usd=cost,
                        confidence="high",
                    )
                )
        return findings
