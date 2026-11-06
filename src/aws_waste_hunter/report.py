"""Report rendering (JSON and Markdown) and private file output."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from aws_waste_hunter.models import ScanSummary

FOOTER = (
    "## What automation can't see\n\n"
    "This scan finds mechanical waste from API metadata. It does not assess architecture, "
    "data-transfer design, commitment strategy (Savings Plans / Reserved Instances) or "
    "workload-level right-sizing. Those need a human review: https://helyxit.com\n"
)


def to_json(summary: ScanSummary) -> str:
    payload = {
        "accounts": summary.accounts,
        "regions": summary.regions,
        "pricing_sources": {r.region: r.pricing_source for r in summary.results},
        "total_estimated_monthly_savings_usd": summary.total_savings_usd,
        "findings": [asdict(f) for f in summary.findings],
        "errors": [asdict(e) for e in summary.errors],
    }
    return json.dumps(payload, indent=2)


def _md_cell(text: str) -> str:
    """Resource names are untrusted input: neutralise Markdown table/HTML injection."""
    return text.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")


def to_markdown(summary: ScanSummary) -> str:
    lines = [
        f"# AWS waste report - {', '.join(summary.regions)}",
        "",
        *([f"Accounts: {', '.join(summary.accounts)}", ""] if len(summary.accounts) > 1 else []),
        f"**Estimated monthly savings: ${summary.total_savings_usd:,.2f}** "
        "(estimates, not a quote)",
        "",
        "Pricing: " + "; ".join(f"{r.region}: `{r.pricing_source}`" for r in summary.results),
        "",
    ]
    findings = summary.findings
    if findings:
        lines += [
            "| Account | Region | Check | Resource | Reason | Cost/mo | Savings/mo | Confidence |",
            "|---|---|---|---|---|---:|---:|---|",
        ]
        for f in findings:
            est = f.estimated_savings_usd
            savings = "n/a" if est is None else f"${est:,.2f}"
            lines.append(
                f"| {f.account_id} | {f.region} | {f.check_id} | `{_md_cell(f.resource_id)}` | "
                f"{_md_cell(f.reason)} | ${f.monthly_cost_usd:,.2f} | {savings} | {f.confidence} |"
            )
    else:
        lines.append("No waste found by the enabled checks.")
    if summary.errors:
        lines += ["", "## Checks that could not run", ""]
        lines += [
            f"- `{e.check_id}` ({e.account_id} {e.region}): {_md_cell(e.message)}"
            for e in summary.errors
        ]
    lines += ["", FOOTER]
    return "\n".join(lines)


def write_private(path: Path, text: str) -> None:
    """Write a report readable only by the current user (reports describe your account)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(path, 0o600)
