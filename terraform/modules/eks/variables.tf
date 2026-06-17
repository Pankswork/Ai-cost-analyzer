# EKS Module variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where EKS will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for EKS node groups"
  type        = list(string)
}

variable "cluster_version" {
  description = "Kubernetes version for EKS cluster"
  type        = string
  default     = "1.36"
}
