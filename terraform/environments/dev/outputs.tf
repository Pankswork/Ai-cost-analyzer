# Dev environment outputs — useful values after terraform apply

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_id
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.db_endpoint
}

output "backend_iam_role_arn" {
  description = "IAM role for the backend service account (IRSA)"
  value       = module.eks.backend_iam_role_arn
}

output "ecr_backend_url" {
  description = "ECR repository URL for backend images"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  description = "ECR repository URL for frontend images"
  value       = aws_ecr_repository.frontend.repository_url
}

output "aws_account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "alb_controller_role_arn" {
  description = "IAM role ARN for the ALB controller (IRSA)"
  value       = module.eks.alb_controller_role_arn
}

output "static_assets_bucket" {
  description = "S3 bucket for frontend static assets"
  value       = aws_s3_bucket.static_assets.bucket
}

output "waf_acl_arn" {
  description = "WAF Web ACL ARN"
  value       = aws_wafv2_web_acl.main.arn
}
