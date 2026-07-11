# Terraform state backend configuration for dev environment
#
# Stores state in S3 for team collaboration and DynamoDB for state locking.
# This prevents concurrent terraform apply operations from conflicting.
#
# Prerequisites:
# - S3 bucket: cost-detective-terraform-state (created manually)
# - DynamoDB table: cost-detective-terraform-locks (created manually)
# -

terraform {
  backend "s3" {
    bucket         = "cost-detective-terraform-state"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "cost-detective-terraform-locks"
    encrypt        = true
  }
}
