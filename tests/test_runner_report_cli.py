from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from aws_waste_hunter import cli, report
from aws_waste_hunter.checks import all_checks
from aws_waste_hunter.models import Finding, ScanResult, ScanSummary
from aws_waste_hunter.pricing import PriceBook
from aws_waste_hunter.readonly import make_session
from aws_waste_hunter.runner import run_scan

ROOT = Path(__file__).resolve().parent.parent
POLICY = json.loads((ROOT / "iam" / "policy.json").read_text())
POLICY_ACTIONS = {a for s in POLICY["Statement"] for a in s["Action"]}


def test_every_check_action_is_in_the_published_iam_policy() -> None:
    for check in all_checks():
        missing = set(check.required_actions) - POLICY_ACTIONS
        assert not missing, f"{check.id} needs actions missing from iam/policy.json: {missing}"


class _Denied:
    id: ClassVar[str] = "denied"
    required_actions: ClassVar[tuple[str, ...]] = ()

    def run(self, session: Any, region: str, prices: PriceBook) -> list[Finding]:
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "DescribeX")


@mock_aws
def test_failed_check_is_reported_not_raised() -> None:
    session = make_session(region_name="us-east-1")
    result = run_scan(session, "us-east-1", checks=[_Denied(), *all_checks()])
    assert [e.check_id for e in result.errors] == ["denied"]
    assert "AccessDenied" in result.errors[0].message


@mock_aws
def test_scan_end_to_end_sorted_by_savings() -> None:
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3")
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=1000, VolumeType="gp3")
    ec2.allocate_address(Domain="vpc")
    result = run_scan(make_session(region_name="us-east-1"), "us-east-1")
    savings = [f.estimated_savings_usd or 0 for f in result.findings]
    assert savings == sorted(savings, reverse=True)
    assert result.total_savings_usd == pytest.approx(80.0 + 0.8 + 3.65)


def _result_with(resource: str) -> ScanSummary:
    r = ScanResult(region="us-east-1", pricing_source="test")
    r.findings.append(Finding("c", resource, "us-east-1", "why", "do", 1.0, None, "low"))
    return ScanSummary(results=[r])


def test_json_report_roundtrips() -> None:
    data = json.loads(report.to_json(_result_with("vol-1")))
    assert data["findings"][0]["resource_id"] == "vol-1"
    assert data["findings"][0]["estimated_savings_usd"] is None


def test_markdown_escapes_untrusted_names() -> None:
    md = report.to_markdown(_result_with("a|b <script>alert(1)</script>\nx"))
    assert "<script>" not in md
    assert "a\\|b" in md
    assert "helyxit.com" in md


@mock_aws
def test_cli_writes_report_and_exit_code(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    argv = ["scan", "--region", "us-east-1", "--pricing", "offline", "--format", "json"]
    code = cli.main([*argv, "--output", str(out)])
    assert code == 0
    assert json.loads(out.read_text())["regions"] == ["us-east-1"]
    assert (out.stat().st_mode & 0o777) == 0o600  # reports describe your account


@mock_aws
def test_cli_multiple_regions_and_all_regions(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    base = ["scan", "--pricing", "offline", "--format", "json", "--output", str(out)]
    assert cli.main([*base, "--regions", "us-east-1,eu-west-1,us-east-1"]) == 0
    assert json.loads(out.read_text())["regions"] == ["us-east-1", "eu-west-1"]
    assert cli.main([*base, "--all-regions"]) == 0
    assert "us-east-1" in json.loads(out.read_text())["regions"]


@pytest.mark.parametrize("bad", ["us-east-1/../x", "evil.com#", "", "US-EAST-1", "us-east"])
def test_cli_rejects_invalid_region(bad: str) -> None:
    with pytest.raises(SystemExit):
        cli.main(["scan", "--region", bad])


def test_cli_requires_exactly_one_region_option() -> None:
    with pytest.raises(SystemExit):
        cli.main(["scan"])
    with pytest.raises(SystemExit):
        cli.main(["scan", "--region", "us-east-1", "--all-regions"])
