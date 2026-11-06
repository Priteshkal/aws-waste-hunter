variable "trusted_principal_arns" {
  type        = list(string)
  description = "IAM role/user ARNs allowed to assume the scanner role (never use account root or *)."

  validation {
    condition     = length(var.trusted_principal_arns) > 0 && alltrue([for a in var.trusted_principal_arns : can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:(role|user)/.+", a))])
    error_message = "Provide specific IAM role or user ARNs."
  }
}

variable "external_id" {
  type        = string
  sensitive   = true
  description = "ExternalId required to assume the role (confused-deputy protection). Use a long random value."

  validation {
    condition     = length(var.external_id) >= 16
    error_message = "external_id must be at least 16 characters."
  }
}

variable "role_name" {
  type    = string
  default = "aws-waste-hunter-scanner"
}

variable "tags" {
  type    = map(string)
  default = {}
}
