# RDS Module variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where RDS will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for RDS subnet group"
  type        = list(string)
}

variable "cluster_security_group_id" {
  description = "EKS cluster security group ID (allows PostgreSQL access)"
  type        = string
}

variable "database_name" {
  description = "Name of the PostgreSQL database"
  type        = string
  default     = "cost_detective"
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "node_security_group_id" {
  description = "EKS node security group ID (allows pod-to-RDS traffic)"
  type        = string
}
