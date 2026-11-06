"""Registry of built-in checks."""

from __future__ import annotations

from aws_waste_hunter.checks.base import Check
from aws_waste_hunter.checks.ebs_gp2 import Gp2ToGp3
from aws_waste_hunter.checks.ebs_unattached import UnattachedEbsVolumes
from aws_waste_hunter.checks.eip_unassociated import UnassociatedElasticIps
from aws_waste_hunter.checks.log_retention import LogGroupsWithoutRetention


def all_checks() -> list[Check]:
    return [
        UnattachedEbsVolumes(),
        Gp2ToGp3(),
        UnassociatedElasticIps(),
        LogGroupsWithoutRetention(),
    ]
