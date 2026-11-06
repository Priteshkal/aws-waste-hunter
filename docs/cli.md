# CLI reference

```
aws-waste-hunter scan (--region R | --regions R1,R2 | --all-regions) [options]
```

| Option | Description |
|---|---|
| `--region REGION` | Scan one region, e.g. `us-east-1` |
| `--regions R1,R2` | Scan a comma-separated list of regions |
| `--all-regions` | Scan every region enabled for the account |
| `--profile NAME` | AWS profile or SSO profile name (standard credential chain otherwise) |
| `--role-arn ARN` | Assume this read-only role to scan another account. Repeat for more accounts |
| `--external-id ID` | ExternalId used for every `--role-arn` |
| `--format json\|md` | Report format (default `md`) |
| `--output PATH` | Write the report to a private (`0600`) file instead of stdout |
| `--pricing live\|offline` | `live` uses the AWS Price List API with a 24h cache and offline fallback (default) |
| `--concurrency N` | Parallel scans, 1-16 (default 8) |
| `--max-metrics N` | CloudWatch metric queries allowed per account and region, 0-5000 (default 200) |

Exactly one of `--region`, `--regions` and `--all-regions` is required. Region names and role
ARNs are validated before any AWS call.

## Exit codes
| Code | Meaning |
|---|---|
| `0` | Scan completed with no check errors (findings do not change the exit code) |
| `1` | At least one check failed, for example a missing permission or an exhausted metric budget. The report lists every failure |
| `2` | Could not start: for example the role could not be assumed or the ExternalId was refused |

## Examples
```bash
aws-waste-hunter scan --region us-east-1 --profile my-sso-profile
aws-waste-hunter scan --regions us-east-1,eu-west-1 --format json --output report.json
aws-waste-hunter scan --all-regions --concurrency 12
aws-waste-hunter scan --region us-east-1 --pricing offline      # no Price List calls
aws-waste-hunter scan --region us-east-1 --max-metrics 50       # tighter CloudWatch cap
```

## Reading the report
Findings are sorted by estimated monthly savings. Each row has the account, region, check,
resource, reason, current cost, estimated savings and a confidence level. The header states
which pricing source was used per region. Amounts are estimates, not quotes.
See the [sample report](sample-report.md).
