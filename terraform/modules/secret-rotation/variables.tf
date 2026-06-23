variable "environment" {
  description = "Environment name"
  type        = string
}

variable "secret_arn" {
  description = "ARN of the Secrets Manager secret to rotate"
  type        = string
}

variable "source_dir" {
  description = "Directory containing the Lambda Python source"
  type        = string
  default     = "../../../lambda/secret-rotation"
}
