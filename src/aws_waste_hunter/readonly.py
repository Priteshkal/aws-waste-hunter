"""Read-only enforcement for every AWS call this tool makes.

The tool must never mutate an AWS account. Two layers enforce that:

1. ``ALLOWED_OPERATION_PREFIXES`` - botocore operation names must start with one of these.
2. ``make_session`` installs a ``before-call`` hook that raises ``ReadOnlyViolation`` for
   anything else, so a coding mistake fails loudly instead of changing an account.

The IAM policy in ``iam/policy.json`` is the third layer: even if both of the above were
bypassed, the role has no write permissions.
"""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config

from aws_waste_hunter.regions import validate_region

# CamelCase botocore operation names (e.g. "DescribeVolumes"). Deliberately tiny.
ALLOWED_OPERATION_PREFIXES: tuple[str, ...] = ("Describe", "List", "Get")


class ReadOnlyViolation(RuntimeError):  # noqa: N818 - public name reads better
    """Raised when code attempts an AWS operation outside the read-only allowlist."""


def is_read_only_operation(operation_name: str) -> bool:
    """Return True if a botocore operation name is on the read-only allowlist."""
    return operation_name.startswith(ALLOWED_OPERATION_PREFIXES)


def _guard(model: Any, **_: Any) -> None:
    if not is_read_only_operation(model.name):
        raise ReadOnlyViolation(
            f"Blocked non-read-only AWS operation: {model.service_model.service_name}."
            f"{model.name}. aws-waste-hunter only permits {ALLOWED_OPERATION_PREFIXES}."
        )


def make_session(**kwargs: Any) -> boto3.session.Session:
    """Create a boto3 session whose clients refuse any non-read-only call.

    Uses the standard AWS credential chain (env, SSO, shared config). Credentials are never
    read, stored or logged by this project.
    """
    session = boto3.session.Session(**kwargs)
    session.events.register("before-call.*.*", _guard)
    return session


# Bounded timeouts and retries so a hung or throttled endpoint cannot stall or hammer AWS.
CLIENT_CONFIG = Config(
    connect_timeout=5,
    read_timeout=30,
    retries={"max_attempts": 5, "mode": "standard"},
)


def client(session: Any, service: str, region: str) -> Any:
    """The only way checks should create AWS clients: validated region, bounded timeouts."""
    return session.client(service, region_name=validate_region(region), config=CLIENT_CONFIG)
