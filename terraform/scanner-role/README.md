# scanner-role

Creates a read-only role that `aws-waste-hunter` assumes in a target account.

```hcl
module "waste_hunter_role" {
  source                 = "github.com/Priteshkal/aws-waste-hunter//terraform/scanner-role"
  trusted_principal_arns = ["arn:aws:iam::111111111111:role/waste-hunter-runner"]
  external_id            = var.waste_hunter_external_id # >= 16 random chars
}
```

Then, from the trusted principal:

```bash
aws-waste-hunter scan --all-regions \
  --role-arn arn:aws:iam::222222222222:role/aws-waste-hunter-scanner \
  --external-id "$WASTE_HUNTER_EXTERNAL_ID"
```

The principal running the scan also needs `sts:AssumeRole` on this role in its own account's
IAM policy. The role grants only `iam/policy.json` (Describe/List/Get, no wildcards).
