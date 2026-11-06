# Checks

Every check is read-only. Its required IAM actions are listed here and must appear in
[`iam/policy.json`](../iam/policy.json); a test fails if they drift apart.

| ID | What it finds | How it decides | Savings | Confidence | IAM actions |
|---|---|---|---|---|---|
| `ebs-unattached` | EBS volumes not attached to anything | `State` is `available` | Full monthly volume cost | high | `ec2:DescribeVolumes` |
| `ebs-gp2-to-gp3` | In-use gp2 volumes | gp2 volumes that are attached | gp2 price minus gp3 price (about 20%) | medium | `ec2:DescribeVolumes` |
| `eip-unassociated` | Elastic IPs allocated but unused | No association, instance or network interface | Idle public IPv4 price (about $3.65/month in us-east-1) | high | `ec2:DescribeAddresses` |
| `logs-no-retention` | CloudWatch log groups that never expire | No `retentionInDays` | Not estimated: depends on the retention you choose | low | `logs:DescribeLogGroups` |
| `nat-idle` | NAT gateways carrying no traffic | `BytesOutToDestination` + `BytesInFromSource` sum to 0 over 7 days; gateway older than 7 days | Full hourly cost (list price) | medium | `ec2:DescribeNatGateways`, `cloudwatch:GetMetricData` |
| `lb-idle` | ALBs and NLBs with no traffic | `ProcessedBytes` sums to 0 over 7 days; balancer older than 7 days | Full hourly cost (list price) | medium | `elasticloadbalancing:DescribeLoadBalancers`, `cloudwatch:GetMetricData` |

## Notes on each check
- **`ebs-gp2-to-gp3`** only reports volumes in use. Unattached gp2 volumes are covered by
  `ebs-unattached`, so nothing is counted twice.
- **`logs-no-retention`** has no savings figure on purpose: the right retention depends on your
  compliance needs.
- **Metric checks (`nat-idle`, `lb-idle`)** never judge a resource younger than the 7-day
  window, because it has no history yet. They use `ProcessedBytes` for load balancers because
  balancers that answer with fixed responses or redirects publish no `RequestCount` (found by
  testing against a real account).
- **Metric cost cap.** CloudWatch bills about $0.01 per 1,000 metrics requested. Each query is
  charged against `--max-metrics` (default 200 per account and region, about $0.002) *before*
  it is made. When the cap is reached the check stops, keeps what it found, and reports an
  error.
- **Dollar figures for metric checks** use us-east-1 list prices, so treat them as estimates.

## What is not covered (yet)
Idle EC2 and RDS, S3 lifecycle gaps, old snapshots and AMIs, ECR images, Savings Plans and
Reserved Instance coverage, and EKS right-sizing. See the roadmap in the README.
