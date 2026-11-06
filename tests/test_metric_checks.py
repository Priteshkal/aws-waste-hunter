from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from aws_waste_hunter import metrics
from aws_waste_hunter.checks.lb_idle import IdleLoadBalancers
from aws_waste_hunter.checks.nat_idle import IdleNatGateways
from aws_waste_hunter.metrics import MetricBudget, MetricBudgetExceeded
from aws_waste_hunter.pricing import PriceBook
from aws_waste_hunter.readonly import make_session
from aws_waste_hunter.runner import run_scan

REGION = "us-east-1"
PRICES = PriceBook()
OLD = datetime.now(timezone.utc) - timedelta(days=30)


def _session() -> Any:
    return make_session(region_name=REGION)


def _nat() -> str:
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    sub = ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.0.0/24")["Subnet"]["SubnetId"]
    eip = ec2.allocate_address(Domain="vpc")["AllocationId"]
    return ec2.create_nat_gateway(SubnetId=sub, AllocationId=eip)["NatGateway"]["NatGatewayId"]


def _old_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "aws_waste_hunter.checks.nat_idle.lookback_start", lambda: OLD + timedelta(days=60)
    )
    monkeypatch.setattr(
        "aws_waste_hunter.checks.lb_idle.lookback_start", lambda: OLD + timedelta(days=60)
    )


@mock_aws
def test_idle_nat_found_with_dollar_math(monkeypatch: pytest.MonkeyPatch) -> None:
    _old_enough(monkeypatch)
    nat = _nat()
    with patch.object(metrics, "client") as c:
        c.return_value.get_metric_data.return_value = {"MetricDataResults": []}
        findings = IdleNatGateways().run(_session(), REGION, PRICES, MetricBudget())
    assert [f.resource_id for f in findings] == [nat]
    assert findings[0].monthly_cost_usd == 32.85  # 0.045 * 730
    assert findings[0].confidence == "medium"


@mock_aws
def test_busy_nat_not_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _old_enough(monkeypatch)
    _nat()

    def fake(**kw: Any) -> dict[str, Any]:
        return {
            "MetricDataResults": [{"Id": q["Id"], "Values": [1e9]} for q in kw["MetricDataQueries"]]
        }

    with patch.object(metrics, "client") as c:
        c.return_value.get_metric_data.side_effect = fake
        assert IdleNatGateways().run(_session(), REGION, PRICES, MetricBudget()) == []


@mock_aws
def test_new_nat_is_not_judged() -> None:
    _nat()  # created just now: no 7-day history, must not be flagged
    with patch.object(metrics, "client") as c:
        assert IdleNatGateways().run(_session(), REGION, PRICES, MetricBudget()) == []
        c.return_value.get_metric_data.assert_not_called()


@mock_aws
def test_idle_alb_found_and_new_one_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    subs = [
        ec2.create_subnet(VpcId=vpc, CidrBlock=f"10.0.{i}.0/24", AvailabilityZone=f"us-east-1{z}")[
            "Subnet"
        ]["SubnetId"]
        for i, z in enumerate("ab")
    ]
    elb = boto3.client("elbv2", region_name=REGION)
    elb.create_load_balancer(Name="idle-alb", Subnets=subs, Type="application")
    with patch.object(metrics, "client") as c:
        assert IdleLoadBalancers().run(_session(), REGION, PRICES, MetricBudget()) == []  # new
        _old_enough(monkeypatch)
        c.return_value.get_metric_data.return_value = {"MetricDataResults": []}
        findings = IdleLoadBalancers().run(_session(), REGION, PRICES, MetricBudget())
    assert [f.resource_id for f in findings] == ["idle-alb"]
    assert findings[0].monthly_cost_usd == 16.43


def test_budget_blocks_before_the_call() -> None:
    b = MetricBudget(max_metrics=3)
    b.charge(3)
    with pytest.raises(MetricBudgetExceeded):
        b.charge(1)
    assert b.used == 3
    assert b.estimated_cost_usd == 0.00003


@mock_aws
def test_budget_exhaustion_is_reported_and_keeps_partial_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _old_enough(monkeypatch)
    _nat()
    _nat()
    with patch.object(metrics, "client") as c:
        c.return_value.get_metric_data.return_value = {"MetricDataResults": []}
        # budget of 2 = exactly one NAT (2 metrics); the second must stop the check.
        res = run_scan(_session(), REGION, [IdleNatGateways()], PRICES, max_metrics=2)
    assert len(res.findings) == 1
    assert len(res.errors) == 1 and "budget" in res.errors[0].message
    assert c.return_value.get_metric_data.call_count == 1  # never queried beyond the cap
