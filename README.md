# aws-waste-hunter

Read-only, auditable AWS waste scanner that estimates the dollars you could save.
Built by [Helyx IT](https://helyxit.com).

> **Status:** pre-alpha (slice 1). One region per scan, four checks.

## Usage
```bash
pip install -e .
aws-waste-hunter scan --region us-east-1 --profile my-sso-profile --format md
```
Attach the policy in [`iam/policy.json`](iam/policy.json) to the role you scan with.

## Checks
| ID | Finds |
|---|---|
| `ebs-unattached` | EBS volumes not attached to anything |
| `ebs-gp2-to-gp3` | in-use gp2 volumes that could be gp3 (~20% cheaper) |
| `eip-unassociated` | Elastic IPs allocated but not associated |
| `logs-no-retention` | CloudWatch log groups that never expire |

Dollar amounts use an offline us-east-1 list-price table (labelled in every report);
treat them as estimates. A check that fails (e.g. missing permission) is listed in the
report and the exit code is 1; it is never silently skipped.

## Principles
- **Read-only**: only `Describe*`/`List*`/`Get*` AWS calls, enforced in code, tests and IAM.
- **Local**: runs on your machine or CI; nothing leaves your account.
- **Auditable**: small codebase, minimal dependencies, published least-privilege IAM policy.

## Develop
```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && mypy src && pytest
```

Tests use [moto](https://github.com/getmoto/moto); no AWS account or credentials needed.

## What automation can't see
This tool finds mechanical waste. Architecture, data-transfer design and commitment strategy
need a human review - that's what Helyx does.

## License
Apache-2.0
