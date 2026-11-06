# aws-waste-hunter

Read-only, auditable AWS waste scanner that tells you **how many dollars** you can save.
Built by [Helyx IT](https://helyxit.com).

> **Status:** pre-alpha (slice 3). Parallel multi-region and cross-account scans, live pricing, six checks including metric-based idle detection with a hard cost cap.

## Why this one
- **It can't change your account.** Every AWS call is `Describe*`, `List*` or `Get*`, enforced
  three ways: in code, in tests, and in the IAM policy you attach.
- **It runs on your machine.** No SaaS, no agent, no telemetry. Nothing leaves your account.
- **You can read all of it.** Small codebase, minimal dependencies, published least-privilege
  IAM policy.
- **It speaks dollars.** Every finding has a monthly cost and a savings estimate, priced from
  the live AWS Price List API.

## Usage
```bash
pip install -e .

aws-waste-hunter scan --region us-east-1 --profile my-sso-profile
aws-waste-hunter scan --regions us-east-1,eu-west-1 --format json --output report.json
aws-waste-hunter scan --all-regions
aws-waste-hunter scan --region us-east-1 --pricing offline   # no Price List calls
aws-waste-hunter scan --region us-east-1 --max-metrics 50    # tighter CloudWatch cost cap
aws-waste-hunter scan --all-regions --concurrency 12         # parallel (default 8, max 16)

# Other accounts: assume a read-only role in each (repeat --role-arn for more accounts)
aws-waste-hunter scan --all-regions \
  --role-arn arn:aws:iam::222222222222:role/aws-waste-hunter-scanner \
  --external-id "$WASTE_HUNTER_EXTERNAL_ID"
```
Create the cross-account role with the Terraform module in
[`terraform/scanner-role`](terraform/scanner-role): trust is limited to the principals you list
and requires an ExternalId; permissions are exactly [`iam/policy.json`](iam/policy.json).
Attach [`iam/policy.json`](iam/policy.json) to the role you scan with. Reports are written
with `0600` permissions because they describe your account.

## Checks
| ID | Finds |
|---|---|
| `ebs-unattached` | EBS volumes not attached to anything |
| `ebs-gp2-to-gp3` | in-use gp2 volumes that could be gp3 (~20% cheaper) |
| `eip-unassociated` | Elastic IPs allocated but not associated |
| `logs-no-retention` | CloudWatch log groups that never expire |
| `nat-idle` | NAT gateways (older than 7 days) that moved 0 bytes in the last 7 days |
| `lb-idle` | Application/Network load balancers (older than 7 days) with no traffic in 7 days |

`nat-idle` and `lb-idle` read CloudWatch (`GetMetricData`, billed ~$0.01 per 1,000 metrics).
Every query is charged against a budget first: `--max-metrics` (default 200 per account and
region, about $0.002). If the cap is reached the check stops, keeps what it found, and reports
the error. Their dollar figures use us-east-1 list prices, so treat them as estimates.

A check that fails (for example a missing permission) is listed in the report and the exit
code is 1. It is never silently skipped.

## Pricing
Prices come from the AWS Price List API per region, are cached for 24 hours, and fall back to
an offline us-east-1 list-price table if the lookup fails. Every report states which source
was used. Live and cached values must be positive and within a sane band of the reference, so
a bad parse or a tampered cache cannot inflate your numbers. Amounts are estimates, not quotes.

## Security model
- Read-only guard on every call, plus a CI test that fails on any other operation.
- Least-privilege IAM policy with no wildcards; every check's required actions are
  test-verified against it.
- AWS clients can only be created through one guarded helper (bounded timeouts, bounded
  retries, validated region); a test fails if any other code creates a raw client.
- Region names are validated before they reach endpoints or file paths.
- Resource names and tags are treated as untrusted input when rendering reports.
- Cross-account scans use short-lived (1h) assumed-role credentials that stay in memory; the
  only non-read operation allowed through the guard is the exact `sts:AssumeRole`.
- Standard AWS credential chain / SSO only. Credentials are never stored, logged or sent.
- GitHub Actions are pinned to commit SHAs.

See [SECURITY.md](SECURITY.md) to report a vulnerability.

---

# Pro (planned)

The open-source scanner finds the mechanical waste. **Pro** is where it becomes a savings
program. These features are on the roadmap and are **not available yet**; the order below is
the rough build order.

### Find more, across everything
- **Org-wide scans.** Cross-account scanning works today with `--role-arn`; Pro adds automatic
  discovery of every account in your AWS Organization.
- **More metric-based idle detection.** Idle EC2 and RDS (NAT gateways and load balancers
  are already in the open-source scanner). The waste that metadata alone can't show, with a hard cost cap
  so the scan itself never surprises you.
- **EKS right-sizing.** Requests vs real usage from Datadog or Prometheus, plus the
  autoscaler blockers that keep nodes alive. The same playbook behind a 70%+ node reduction.
- **Commitment review.** Savings Plans and Reserved Instance coverage, usually the single
  biggest lever.

### Fix it safely
- **Fix-as-code merge requests.** Generates the Terraform or CLI change as a GitLab or
  GitHub MR for a human to review. It never applies anything itself.
- **Terraform cost guard.** Estimates the monthly cost of every `terraform plan` and flags
  expensive patterns before they merge.
- **Suppressions with expiry.** Accept a finding per resource or tag, with an owner and a
  review date, kept as policy-as-code in your repo.

### Prove the savings
- **Trend history and scheduled scans.** Weekly digests to Slack or email and a running total
  of dollars saved, so the program has numbers behind it.
- **AI prioritization in your own account.** Ranks findings by effort versus payoff using
  Bedrock (or a local model). The AI only summarizes: it never detects and never acts, and
  nothing leaves your account.
- **Export anywhere.** SARIF, CSV and Jira.

### Don't want to run it yourself?
Helyx does manual, expert-led AWS reviews with a guaranteed 15% savings, and goes where
automation can't: architecture, data-transfer design and commitment strategy.
[Book a call](https://helyxit.com).

## Develop
```bash
python3.13 -m venv ~/.venvs/aws-waste-hunter && source ~/.venvs/aws-waste-hunter/bin/activate
pip install -e ".[dev]"
ruff check . && mypy src && pytest
```
Tests use [moto](https://github.com/getmoto/moto) and canned Price List responses; no AWS
account or credentials needed.

## License
Apache-2.0
