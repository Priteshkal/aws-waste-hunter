"""Report rendering (JSON and Markdown)."""

from __future__ import annotations

import json
from dataclasses import asdict

from aws_waste_hunter.models import ScanResult

FOOTER = (
    "## What automation can't see\n\n"
    "This scan finds mechanical waste from API metadata. It does not assess architecture, "
    "data-transfer design, commitment strategy (Savings Plans / Reserved Instances) or "
    "workload-level right-sizing. Those need a human review: https://helyxit.com\n"
)


def to_json(result: ScanResult) -> str:
    payload = {
        "region": result.region,
        "pricing_source": result.pricing_source,
        "total_estimated_monthly_savings_usd": result.total_savings_usd,
        "findings": [asdict(f) for f in result.findings],
        "errors": [asdict(e) for e in result.errors],
    }
    return json.dumps(payload, indent=2)


def _md_cell(text: str) -> str:
    """Resource names are untrusted input: neutralise Markdown table/HTML injection."""
    return text.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")


def to_markdown(result: ScanResult) -> str:
    lines = [
        f"# AWS waste report - {result.region}",
        "",
        f"**Estimated monthly savings: ${result.total_savings_usd:,.2f}** "
        f"(pricing: `{result.pricing_source}`; estimates, not a quote)",
        "",
    ]
    if result.findings:
        lines += [
            "| Check | Resource | Reason | Cost/mo | Savings/mo | Confidence |",
            "|---|---|---|---:|---:|---|",
        ]
        for f in result.findings:
            est = f.estimated_savings_usd
            savings = "n/a" if est is None else f"${est:,.2f}"
            lines.append(
                f"| {f.check_id} | `{_md_cell(f.resource_id)}` | {_md_cell(f.reason)} | "
                f"${f.monthly_cost_usd:,.2f} | {savings} | {f.confidence} |"
            )
    else:
        lines.append("No waste found by the enabled checks.")
    if result.errors:
        lines += ["", "## Checks that could not run", ""]
        lines += [f"- `{e.check_id}`: {_md_cell(e.message)}" for e in result.errors]
    lines += ["", FOOTER]
    return "\n".join(lines)
