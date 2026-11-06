from __future__ import annotations

import boto3
from moto import mock_aws

from aws_waste_hunter.checks.ebs_gp2 import Gp2ToGp3
from aws_waste_hunter.checks.ebs_unattached import UnattachedEbsVolumes
from aws_waste_hunter.checks.eip_unassociated import UnassociatedElasticIps
from aws_waste_hunter.checks.log_retention import LogGroupsWithoutRetention
from aws_waste_hunter.pricing import PriceBook
from aws_waste_hunter.readonly import make_session

REGION = "us-east-1"
PRICES = PriceBook()


def _session() -> boto3.session.Session:
    return make_session(region_name=REGION)


@mock_aws
def test_unattached_volume_found_with_dollar_math() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=100, VolumeType="gp3")
    findings = UnattachedEbsVolumes().run(_session(), REGION, PRICES)
    assert [f.resource_id for f in findings] == [vol["VolumeId"]]
    assert findings[0].monthly_cost_usd == 8.0  # 100 GiB * $0.08
    assert findings[0].estimated_savings_usd == 8.0
    assert findings[0].confidence == "high"


@mock_aws
def test_no_unattached_volumes_means_no_findings() -> None:
    assert UnattachedEbsVolumes().run(_session(), REGION, PRICES) == []


@mock_aws
def test_attached_volume_is_not_reported_as_unattached() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    inst = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)["Instances"][0]
    vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)
    ec2.attach_volume(VolumeId=vol["VolumeId"], InstanceId=inst["InstanceId"], Device="/dev/sdf")
    ids = [f.resource_id for f in UnattachedEbsVolumes().run(_session(), REGION, PRICES)]
    assert vol["VolumeId"] not in ids


@mock_aws
def test_gp2_in_use_reports_gp3_savings_and_skips_unattached() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    inst = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)["Instances"][0]
    attached = ec2.create_volume(AvailabilityZone="us-east-1a", Size=500, VolumeType="gp2")
    ec2.attach_volume(
        VolumeId=attached["VolumeId"], InstanceId=inst["InstanceId"], Device="/dev/sdf"
    )
    orphan = ec2.create_volume(AvailabilityZone="us-east-1a", Size=500, VolumeType="gp2")
    findings = Gp2ToGp3().run(_session(), REGION, PRICES)
    by_id = {f.resource_id: f for f in findings}
    assert orphan["VolumeId"] not in by_id  # covered by ebs-unattached
    f = by_id[attached["VolumeId"]]
    assert f.monthly_cost_usd == 50.0  # 500 * 0.10
    assert f.estimated_savings_usd == 10.0  # 500 * (0.10 - 0.08)


@mock_aws
def test_gp3_volume_not_flagged() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    inst = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)["Instances"][0]
    vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=50, VolumeType="gp3")
    ec2.attach_volume(VolumeId=vol["VolumeId"], InstanceId=inst["InstanceId"], Device="/dev/sdf")
    ids = [f.resource_id for f in Gp2ToGp3().run(_session(), REGION, PRICES)]
    assert vol["VolumeId"] not in ids


@mock_aws
def test_unassociated_eip_found_and_associated_skipped() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    idle = ec2.allocate_address(Domain="vpc")
    used = ec2.allocate_address(Domain="vpc")
    inst = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)["Instances"][0]
    ec2.associate_address(InstanceId=inst["InstanceId"], AllocationId=used["AllocationId"])
    findings = UnassociatedElasticIps().run(_session(), REGION, PRICES)
    assert [f.resource_id for f in findings] == [idle["AllocationId"]]
    assert findings[0].monthly_cost_usd == 3.65  # $0.005 * 730h


@mock_aws
def test_log_group_without_retention_flagged_and_with_retention_skipped() -> None:
    logs = boto3.client("logs", region_name=REGION)
    logs.create_log_group(logGroupName="/app/forever")
    logs.create_log_group(logGroupName="/app/bounded")
    logs.put_retention_policy(logGroupName="/app/bounded", retentionInDays=30)
    findings = LogGroupsWithoutRetention().run(_session(), REGION, PRICES)
    assert [f.resource_id for f in findings] == ["/app/forever"]
    assert findings[0].estimated_savings_usd is None
    assert findings[0].confidence == "low"
