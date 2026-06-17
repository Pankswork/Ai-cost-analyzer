# VPC Networking Module
#
# Creates the complete VPC infrastructure:
# - VPC with DNS support
# - Public subnets (for ALB, NAT Gateway)
# - Private subnets (for EKS nodes, RDS, Ollama)
# - Internet Gateway, NAT Gateway, route tables
# - VPC Endpoints (S3 Gateway, ECR Interface) to reduce NAT costs
#
# Architecture: 3-AZ for high availability
# CIDR: /16 (room for growth)

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones to use"
  type        = list(string)
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}
