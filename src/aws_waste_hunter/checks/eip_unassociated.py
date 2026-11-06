"""Elastic IPs not associated with anything are billed hourly."""

from __future__ import annotations

from typing import Any, ClassVar

from aws_waste_hunter.models import Finding
from aws_waste_hunter.pricing import PriceBook
from aws_waste_hunter.readonly import client


class UnassociatedElasticIps:
    id: ClassVar[str] = "eip-unassociated"
    required_actions: ClassVar[tuple[str, ...]] = ("ec2:DescribeAddresses",)

    def run(self, session: Any, region: str, prices: PriceBook) -> list[Finding]:
        ec2 = client(session, "ec2", region)
        findings: list[Finding] = []
        for addr in ec2.describe_addresses()["Addresses"]:
            if (
                addr.get("AssociationId")
                or addr.get("InstanceId")
                or addr.get("NetworkInterfaceId")
            ):
                continue
            cost = prices.eip_idle_monthly
            findings.append(
                Finding(
                    check_id=self.id,
                    resource_id=addr.get("AllocationId") or addr["PublicIp"],
                    region=region,
                    reason="Elastic IP is allocated but not associated",
                    recommendation="Release the address if it is no longer needed.",
                    monthly_cost_usd=cost,
                    estimated_savings_usd=cost,
                    confidence="high",
                )
            )
        return findings
