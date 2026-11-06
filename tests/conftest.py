from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fake_aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let tests pick up real credentials."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
