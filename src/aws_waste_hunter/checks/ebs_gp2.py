"""gp2 volumes that can move to gp3: ~20% cheaper per GB with better baseline performance."""

from __future__ import annotations

from typing import Any, ClassVar

from aws_waste_hunter.models import Finding
from aws_waste_hunter.pricing import PriceBook
from aws_waste_hunter.readonly import client


class Gp2ToGp3:
    id: ClassVar[str] = "ebs-gp2-to-gp3"
    required_actions: ClassVar[tuple[str, ...]] = ("ec2:DescribeVolumes",)

    def run(self, session: Any, region: str, prices: PriceBook) -> list[Finding]:
        ec2 = client(session, "ec2", region)
        findings: list[Finding] = []
        pages = ec2.get_paginator("describe_volumes").paginate(
            # 'available' gp2 volumes are reported by ebs-unattached; avoid double counting.
            Filters=[
                {"Name": "volume-type", "Values": ["gp2"]},
                {"Name": "status", "Values": ["in-use"]},
            ]
        )
        for page in pages:
            for vol in page["Volumes"]:
                cost = round(vol["Size"] * prices.ebs_gb_month("gp2"), 2)
                gp3 = round(vol["Size"] * prices.ebs_gb_month("gp3"), 2)
                findings.append(
                    Finding(
                        check_id=self.id,
                        resource_id=vol["VolumeId"],
                        region=region,
                        reason=f"{vol['Size']} GiB gp2 volume could be gp3",
                        recommendation=(
                            "Modify the volume type to gp3 (online, no downtime). Volumes over "
                            "1 TiB or needing >3,000 IOPS / 125 MiB/s baseline may need extra "
                            "provisioned IOPS/throughput; review before migrating."
                        ),
                        monthly_cost_usd=cost,
                        estimated_savings_usd=round(cost - gp3, 2),
                        confidence="medium",
                    )
                )
        return findings
