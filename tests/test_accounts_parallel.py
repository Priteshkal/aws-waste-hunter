from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, ClassVar

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from aws_waste_hunter import cli
from aws_waste_hunter.accounts import (
    Target,
    assume_role_session_kwargs,
    validate_external_id,
    validate_role_arn,
)
from aws_waste_hunter.models import Finding
from aws_waste_hunter.pricing import PriceBook
from aws_waste_hunter.readonly import ReadOnlyViolation, make_session
from aws_waste_hunter.runner import run_multi

ROLE = "arn:aws:iam::123456789012:role/aws-waste-hunter-scanner"
EXT = "0123456789abcdef-external"
REGIONS = ["us-east-1", "eu-west-1", "ap-south-1", "us-west-2"]


def _prices(_session: Any, _region: str) -> PriceBook:
    return PriceBook()


class _BarrierCheck:
    """Only completes if all four regions run at the same time (proves real parallelism)."""

    id: ClassVar[str] = "barrier"
    required_actions: ClassVar[tuple[str, ...]] = ()
    barrier = threading.Barrier(4, timeout=10)

    def run(
        self, session: Any, region: str, prices: PriceBook, budget: Any = None
    ) -> list[Finding]:
        self.barrier.wait()
        return [Finding("barrier", f"r-{region}", region, "x", "y", 1.0, 1.0, "high")]


class _OneFinding:
    id: ClassVar[str] = "one"
    required_actions: ClassVar[tuple[str, ...]] = ()

    def run(
        self, session: Any, region: str, prices: PriceBook, budget: Any = None
    ) -> list[Finding]:
        return [Finding("one", f"r-{region}", region, "x", "y", 1.0, 1.0, "high")]


def test_regions_scan_concurrently_and_keep_input_order() -> None:
    target = Target("111111111111", lambda: object(), REGIONS)
    summary = run_multi([target], _prices, checks=[_BarrierCheck()], concurrency=4)
    assert [r.region for r in summary.results] == REGIONS  # deterministic order
    assert len(summary.findings) == 4 and not summary.errors


def test_each_task_gets_its_own_session_and_account_ids_are_attached() -> None:
    made: list[object] = []

    def factory() -> object:
        made.append(object())
        return made[-1]

    targets = [
        Target("111111111111", factory, REGIONS[:2]),
        Target("222222222222", factory, ["us-east-1"]),
    ]
    summary = run_multi(targets, _prices, checks=[_OneFinding()], concurrency=3)
    assert len(made) == 3 and len({id(m) for m in made}) == 3
    assert summary.accounts == ["111111111111", "222222222222"]
    assert {f.account_id for f in summary.findings} == {"111111111111", "222222222222"}


def test_concurrency_is_clamped() -> None:
    target = Target("111111111111", lambda: object(), REGIONS)
    for value in (0, -5, 10_000):
        assert (
            len(run_multi([target], _prices, checks=[_OneFinding()], concurrency=value).results)
            == 4
        )


@mock_aws
def test_assumed_role_session_scans_as_assumed_identity_and_stays_guarded() -> None:
    kwargs = assume_role_session_kwargs(make_session(region_name="us-east-1"), ROLE, EXT)
    session = make_session(region_name="us-east-1", **kwargs)
    assert (
        "assumed-role/aws-waste-hunter-scanner"
        in session.client("sts").get_caller_identity()["Arn"]
    )
    with pytest.raises(ReadOnlyViolation):
        session.client("ec2").create_volume(AvailabilityZone="us-east-1a", Size=1)


@mock_aws
def test_only_exact_assume_role_is_allowed_through_the_guard() -> None:
    sts = make_session(region_name="us-east-1").client("sts")
    with pytest.raises(ReadOnlyViolation):
        sts.assume_role_with_web_identity(
            RoleArn=ROLE, RoleSessionName="session", WebIdentityToken="token-value"
        )
    with pytest.raises(ReadOnlyViolation):
        sts.assume_role_with_saml(RoleArn=ROLE, PrincipalArn=ROLE, SAMLAssertion="assertion-value")


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "arn:aws:iam::123:role/x",
        "arn:aws:iam::123456789012:user/x",
        "*",
        ROLE + "\n",
        "arn:aws:s3:::b",
    ],
)
def test_invalid_role_arns_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_role_arn(bad)


def test_valid_role_arn_and_external_id() -> None:
    assert validate_role_arn(ROLE) == ROLE
    assert validate_role_arn("arn:aws-us-gov:iam::123456789012:role/path/x")
    assert validate_external_id(EXT) == EXT
    for bad in ["", "a", "has space here", "x" * 1300, "semi;colon"]:
        with pytest.raises(ValueError):
            validate_external_id(bad)


@mock_aws
def test_cli_cross_account_scan(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    argv = [
        "scan",
        "--region",
        "us-east-1",
        "--pricing",
        "offline",
        "--format",
        "json",
        "--role-arn",
        ROLE,
        "--external-id",
        EXT,
        "--output",
        str(out),
    ]
    assert cli.main(argv) == 0
    assert json.loads(out.read_text())["accounts"] == ["123456789012"]


def test_cli_option_validation() -> None:
    with pytest.raises(SystemExit):
        cli.main(["scan", "--region", "us-east-1", "--external-id", EXT])  # needs --role-arn
    with pytest.raises(SystemExit):
        cli.main(["scan", "--region", "us-east-1", "--role-arn", "not-an-arn"])
    with pytest.raises(SystemExit):
        cli.main(["scan", "--region", "us-east-1", "--concurrency", "99"])


def test_cli_assume_role_failure_is_reported_not_hidden(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def deny(*_a: Any, **_k: Any) -> dict[str, str]:
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "AssumeRole")

    monkeypatch.setattr(cli, "assume_role_session_kwargs", deny)
    assert (
        cli.main(["scan", "--region", "us-east-1", "--role-arn", ROLE, "--pricing", "offline"]) == 2
    )
    assert "AccessDenied" in capsys.readouterr().err


def test_terraform_role_module_is_locked_down() -> None:
    tf = Path(__file__).resolve().parent.parent / "terraform" / "scanner-role"
    main = (tf / "main.tf").read_text()
    assert "sts:ExternalId" in main  # confused-deputy protection is mandatory
    assert "iam/policy.json" in main  # permissions are exactly the audited policy
    assert '"*"' not in main
    assert "can(regex" in (tf / "variables.tf").read_text()  # no account-root / wildcard trust
