# Terraform version and provider configuration
# This file is included by all root modules to ensure consistent versions

terraform {
  # Use Terraform 1.9+ for latest features
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "5.94.1"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "2.17.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "2.35.1"
    }
  }
}

# AWS provider configuration — uses IRSA or environment credentials
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "ai-cost-detective"
    }
  }
}
