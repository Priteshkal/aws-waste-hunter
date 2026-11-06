"""Tests that make the 'read-only' claim verifiable."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from aws_waste_hunter.readonly import (
    ALLOWED_OPERATION_PREFIXES,
    ReadOnlyViolation,
    is_read_only_operation,
    make_session,
)

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "iam" / "policy.json"
SRC = ROOT / "src" / "aws_waste_hunter"


@pytest.mark.parametrize("op", ["DescribeVolumes", "ListBuckets", "GetProducts"])
def test_allows_read_operations(op: str) -> None:
    assert is_read_only_operation(op)


@pytest.mark.parametrize(
    "op", ["DeleteVolume", "TerminateInstances", "PutObject", "CreateSnapshot", "ModifyVolume", ""]
)
def test_blocks_write_operations(op: str) -> None:
    assert not is_read_only_operation(op)


@mock_aws
def test_session_allows_describe_and_blocks_mutation() -> None:
    session = make_session(region_name="us-east-1")
    ec2 = session.client("ec2")
    assert ec2.describe_volumes()["Volumes"] == []
    with pytest.raises(ReadOnlyViolation):
        ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)


@mock_aws
def test_session_blocks_s3_writes() -> None:
    # Prove the guard really sits in front of a real mutation, not just a mocked name check.
    plain = boto3.client("s3", region_name="us-east-1")
    plain.create_bucket(Bucket="victim")
    plain.put_object(Bucket="victim", Key="k", Body=b"x")
    guarded = make_session(region_name="us-east-1").client("s3")
    with pytest.raises(ReadOnlyViolation):
        guarded.delete_object(Bucket="victim", Key="k")
    assert plain.get_object(Bucket="victim", Key="k")["Body"].read() == b"x"


def test_iam_policy_is_read_only_and_has_no_wildcards() -> None:
    policy = json.loads(POLICY.read_text())
    for stmt in policy["Statement"]:
        assert stmt["Effect"] == "Allow"
        for action in stmt["Action"]:
            service, _, name = action.partition(":")
            assert service and name, action
            assert "*" not in action, f"wildcard action not allowed: {action}"
            assert name.startswith(ALLOWED_OPERATION_PREFIXES), f"non-read action: {action}"


def _snake(op: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", op).lower()


def test_source_never_calls_mutating_boto_methods() -> None:
    """Static backstop: no call in src/ may use a mutating-verb method name."""
    forbidden = re.compile(
        r"^(create|delete|put|update|modify|terminate|stop|start|run|attach|detach|associate|"
        r"disassociate|release|allocate|copy|deregister|register|tag|untag|set|remove|revoke|"
        r"authorize|invoke|publish|send|reboot|enable|disable|restore|import|export)_"
    )
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if forbidden.match(node.func.attr):
                    offenders.append(f"{path.name}:{node.lineno} .{node.func.attr}()")
    assert not offenders, offenders


def test_allowed_prefixes_are_exactly_read_verbs() -> None:
    assert ALLOWED_OPERATION_PREFIXES == ("Describe", "List", "Get")
