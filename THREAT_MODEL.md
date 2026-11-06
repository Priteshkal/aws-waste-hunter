# Threat model

aws-waste-hunter reads metadata about your AWS account and writes a report. This document
states what it protects, who might attack it, and what stops them. If you find a gap, see
[SECURITY.md](SECURITY.md).

## Assets
- Your AWS credentials and the account's resource inventory (names, IDs, tags, sizes).
- The integrity of the numbers in the report.

## Trust boundaries
- **Your machine / CI runner** runs the tool with your credentials. Nothing runs elsewhere.
- **AWS APIs** are the only network peer (STS, EC2, ELBv2, Logs, CloudWatch, Pricing).
- **Resource names and tags** come from AWS but may be attacker-influenced: untrusted input.

## Threats and controls
| Threat | Control |
|---|---|
| The tool (or a bug in it) modifies the account | Guard on every call allows only `Describe*`, `List*`, `Get*` and exact `AssumeRole`; CI test scans the source for mutating calls; the published IAM policy has no write actions and no wildcards (test-enforced); proven against a real policy-only role |
| A new check needs a permission that isn't in the policy | Test: every check's `required_actions` must be in `iam/policy.json` |
| Credentials or data leave the machine | No telemetry; test fails if the source imports any network or subprocess module other than boto3; credentials come only from the standard AWS chain and are never logged or written |
| Confused deputy via cross-account roles | ExternalId required by the Terraform role module; assumed credentials live 1h, in memory only |
| Malicious resource names (Markdown/HTML injection in reports) | Names escaped when rendering; JSON output is data only |
| Poisoned price data inflates savings | Live and cached prices must be positive and within 0.25x-4x of an offline reference; cache is 0600; source is stated in every report |
| Runaway cost from the scan itself | Metric queries are charged to a hard budget (`--max-metrics`) before each call |
| Path traversal or endpoint injection through `--region` | Strict region regex before any AWS call or file path use |
| Other users on the machine read reports | Reports and cache written with 0600 permissions |
| Supply-chain: malicious dependency or workflow action | Few runtime dependencies; hash-pinned `requirements.lock`; `pip-audit` in CI; GitHub Actions pinned to commit SHAs; Dependabot; gitleaks in CI |

## Out of scope
- A compromised machine or a malicious AWS administrator.
- Savings estimates are not quotes; they use list prices and cannot see discounts or commitments.
- Future AI features will be designed with prompt-injection tests before they ship; none exist today.
