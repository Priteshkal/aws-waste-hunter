output "role_arn" {
  value       = aws_iam_role.scanner.arn
  description = "Pass to: aws-waste-hunter scan --role-arn <this> --external-id <your external id>"
}
