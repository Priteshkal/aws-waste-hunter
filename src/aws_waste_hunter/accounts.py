"""Cross-account scanning: assume a read-only role in each target account.

Credentials are short-lived (1h), held in memory only, and never printed or written to disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from aws_waste_hunter.readonly import client, make_session

_ROLE_ARN_RE = re.compile(r"^arn:aws(-[a-z]+)*:iam::\d{12}:role/[\w+=,.@/-]{1,512}$")
_EXTERNAL_ID_RE = re.compile(r"^[\w+=,.@:/-]{2,1224}$")
SESSION_NAME = "aws-waste-hunter"


def validate_role_arn(arn: str) -> str:
    if not _ROLE_ARN_RE.fullmatch(arn):
        raise ValueError(f"invalid IAM role ARN: {arn!r}")
    return arn


def validate_external_id(value: str) -> str:
    if not _EXTERNAL_ID_RE.fullmatch(value):
        raise ValueError("invalid external id (2-1224 chars: letters, digits, +=,.@:/_-)")
    return value


@dataclass(frozen=True)
class Target:
    """One account to scan. ``session_factory`` returns a fresh guarded session per worker
    because boto3 sessions are not thread-safe."""

    account_id: str
    session_factory: Any  # Callable[[], Session]
    regions: list[str]


def account_id_of(session: Any) -> str:
    return str(client(session, "sts", "us-east-1").get_caller_identity()["Account"])


def assume_role_session_kwargs(
    base_session: Any, role_arn: str, external_id: str | None
) -> dict[str, str]:
    """Assume ``role_arn`` and return kwargs for building guarded sessions with its credentials."""
    params: dict[str, Any] = {
        "RoleArn": validate_role_arn(role_arn),
        "RoleSessionName": SESSION_NAME,
        "DurationSeconds": 3600,
    }
    if external_id:
        params["ExternalId"] = validate_external_id(external_id)
    creds = client(base_session, "sts", "us-east-1").assume_role(**params)["Credentials"]
    return {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
    }


def session_factory(**kwargs: Any) -> Any:
    return lambda: make_session(**kwargs)
