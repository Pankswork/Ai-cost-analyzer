variable "environment" {
  description = "Environment name"
  type        = string
}

variable "source_dir" {
  description = "Directory containing the Lambda Python source"
  type        = string
  default     = "../../../lambda/log-analysis"
}

variable "log_groups" {
  description = "Comma-separated list of CloudWatch log groups to analyze"
  type        = string
  default     = "/aws/eks/cost-detective/cluster,/aws/rds/cost-detective/error"
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for alerts"
  type        = string
  default     = ""
}

variable "ses_from_email" {
  description = "From email for SES alerts"
  type        = string
  default     = "noreply@bestfreeaifor.com"
}

variable "ses_to_email" {
  description = "To email for SES alerts"
  type        = string
  default     = "admin@bestfreeaifor.com"
}
