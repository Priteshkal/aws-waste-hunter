# Read-only role that aws-waste-hunter assumes to scan this account.
# Trust is limited to the principals you list AND requires the ExternalId.
# The permissions are exactly iam/policy.json: Describe/List/Get only, no wildcards.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = var.trusted_principal_arns
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.external_id]
    }
  }
}

resource "aws_iam_role" "scanner" {
  name                 = var.role_name
  description          = "Read-only role for aws-waste-hunter scans"
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  max_session_duration = 3600
  tags                 = var.tags
}

resource "aws_iam_role_policy" "scanner" {
  name   = "aws-waste-hunter-read-only"
  role   = aws_iam_role.scanner.id
  policy = file("${path.module}/../../iam/policy.json")
}
