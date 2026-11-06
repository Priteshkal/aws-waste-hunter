"""No telemetry: the only network client in src/ is boto3 talking to AWS endpoints."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
FORBIDDEN_MODULES = {
    "requests", "urllib", "urllib3", "http", "httpx", "aiohttp", "socket", "ssl",
    "ftplib", "smtplib", "telnetlib", "xmlrpc", "websockets", "subprocess", "webbrowser",
}  # fmt: skip


def test_source_imports_no_network_or_process_modules() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in FORBIDDEN_MODULES:
                    offenders.append(f"{path.name}:{node.lineno} imports {name}")
    assert not offenders, offenders


def test_source_contains_no_hardcoded_urls_except_docs() -> None:
    allowed = ("https://helyxit.com", "https://github.com/Priteshkal/aws-waste-hunter")
    offenders = []
    for path in SRC.rglob("*.py"):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "http://" in line or "https://" in line:
                if not any(a in line for a in allowed):
                    offenders.append(f"{path.name}:{i}")
    assert not offenders, offenders
