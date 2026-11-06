"""Pricing used for dollar estimates.

Slice 1 ships a static, offline table of AWS public *list* prices for us-east-1 so scans
need no extra API calls or permissions and tests are deterministic. Other regions are
usually within a few percent to ~30% of these figures, so reports label amounts as
estimates and state the pricing source. Live Price List API lookups come in a later slice.
"""

from __future__ import annotations

from dataclasses import dataclass

HOURS_PER_MONTH = 730.0

# $/GB-month by EBS volume type (us-east-1 list price).
_EBS_GB_MONTH: dict[str, float] = {
    "gp2": 0.10,
    "gp3": 0.08,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
    "standard": 0.05,
}


@dataclass(frozen=True)
class PriceBook:
    source: str = "offline-us-east-1-list-price"
    eip_idle_hourly: float = 0.005  # unassociated Elastic IP, $/hour
    logs_storage_gb_month: float = 0.03  # CloudWatch Logs archived storage, $/GB-month

    def ebs_gb_month(self, volume_type: str) -> float:
        return _EBS_GB_MONTH.get(volume_type, _EBS_GB_MONTH["gp2"])

    @property
    def eip_idle_monthly(self) -> float:
        return round(self.eip_idle_hourly * HOURS_PER_MONTH, 2)
