# Security Policy

## Security model
- **Read-only by construction.** Every AWS call goes through a guard that only permits
  `Describe*`, `List*` and `Get*` operations (`src/aws_waste_hunter/readonly.py`). CI fails if
  the shipped IAM policy or the source contains anything else.
- **Least privilege.** `iam/policy.json` lists the exact actions required. No wildcards.
- **No secrets handling.** Uses the standard AWS credential chain / SSO only. The tool never
  stores, logs or transmits credentials.
- **No telemetry.** The tool makes no network calls except to AWS APIs.
- **Untrusted data.** Resource names and tag values are treated as untrusted input.

## Reporting a vulnerability
Email **pritesh@helyxit.com** with the subject "aws-waste-hunter security". Please do not open
a public issue. We aim to acknowledge within 3 business days.

## Supported versions
Pre-release (0.x): only the latest commit on `main` is supported.
