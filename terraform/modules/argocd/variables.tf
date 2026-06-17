# ArgoCD Bootstrap module variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  type        = string
}

variable "cluster_certificate_authority_data" {
  description = "Base64-encoded certificate data"
  type        = string
}

variable "cluster_id" {
  description = "EKS cluster ID"
  type        = string
}
