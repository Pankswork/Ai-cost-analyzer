# EKS module outputs

output "cluster_id" {
  description = "EKS cluster name/ID"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded certificate data for EKS cluster"
  value       = module.eks.cluster_certificate_authority_data
}

output "oidc_provider_arn" {
  description = "OpenID Connect provider ARN for IRSA"
  value       = module.eks.oidc_provider_arn
}

output "cluster_security_group_id" {
  description = "Security group ID attached to the EKS cluster"
  value       = module.eks.cluster_security_group_id
}

output "backend_iam_role_arn" {
  description = "IAM role ARN for the backend service account (IRSA)"
  value       = aws_iam_role.backend.arn
}

output "alb_controller_role_arn" {
  description = "IAM role ARN for the ALB controller (IRSA)"
  value       = aws_iam_role.alb_controller.arn
}
