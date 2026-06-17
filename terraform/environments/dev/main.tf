# Dev environment — root Terraform configuration
#
# This is the entry point for Terraform operations in the dev environment.
# It orchestrates all modules: networking → EKS → RDS → ArgoCD
#
# Apply order: terraform apply -auto-approve
# Destroy order: terraform destroy (reverse order)

# ─── Variables ─────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
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

# ─── Data Sources ──────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

# ─── Kubernetes & Helm Providers (post-EKS) ───────────────────────
# These require EKS cluster to exist, configured via module.eks outputs

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_id]
    command     = "aws"
  }
}

provider "helm" {
  kubernetes = {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_id]
      command     = "aws"
    }
  }
}

# ─── External Secrets Operator ────────────────────────────────────
resource "kubernetes_namespace_v1" "external_secrets" {
  depends_on = [module.eks]
  metadata {
    name = "external-secrets"
    labels = {
      "argocd.argoproj.io/managed-by" = "argocd"
    }
  }
}

resource "helm_release" "external_secrets" {
  name       = "external-secrets"
  repository = "https://charts.external-secrets.io"
  chart      = "external-secrets"
  version    = "0.10.7"
  namespace  = kubernetes_namespace_v1.external_secrets.metadata[0].name

  set = [
    {
      name  = "installCRDs"
      value = "true"
    }
  ]

  depends_on = [module.eks]
}

# ─── Monitoring Namespace ─────────────────────────────────────────
resource "kubernetes_namespace_v1" "monitoring" {
  depends_on = [module.eks]
  metadata {
    name = "monitoring"
    labels = {
      "argocd.argoproj.io/managed-by" = "argocd"
    }
  }
}

# ─── Prometheus + Grafana Stack ───────────────────────────────────
resource "helm_release" "kube_prometheus_stack" {
  name       = "prometheus"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = "60.0.2"
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name

  values = [
    <<-YAML
    grafana:
      adminPassword: admin
      service:
        type: ClusterIP
    prometheus:
      prometheusSpec:
        retention: 7d
        resources:
          requests:
            cpu: "500m"
            memory: "2Gi"
    YAML
  ]

  depends_on = [module.eks]
}

# ─── Networking Layer ──────────────────────────────────────────────

module "networking" {
  source             = "../../modules/networking"
  environment        = var.environment
  aws_region         = var.aws_region
  vpc_cidr           = "10.0.0.0/16"
  availability_zones = var.availability_zones
}

# ─── EKS Cluster Layer ─────────────────────────────────────────────

module "eks" {
  source             = "../../modules/eks"
  environment        = var.environment
  aws_region         = var.aws_region
  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  cluster_version    = "1.36"

  depends_on = [module.networking]
}

# ─── RDS Database Layer ────────────────────────────────────────────

module "rds" {
  source                    = "../../modules/rds"
  environment               = var.environment
  vpc_id                    = module.networking.vpc_id
  private_subnet_ids        = module.networking.private_subnet_ids
  cluster_security_group_id = module.eks.cluster_security_group_id

  depends_on = [module.networking, module.eks]
}

# ─── ECR Repositories ──────────────────────────────────────────────

# checkov:skip=CKV_AWS_51:MUTABLE required for CD workflow to push latest tag
resource "aws_ecr_repository" "backend" {
  name                 = "backend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
  }

  tags = {
    Name        = "backend"
    Environment = var.environment
  }
}

# checkov:skip=CKV_AWS_51:MUTABLE required for CD workflow to push latest tag
resource "aws_ecr_repository" "frontend" {
  name                 = "frontend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
  }

  tags = {
    Name        = "frontend"
    Environment = var.environment
  }
}

# ─── S3 Static Assets Bucket ───────────────────────────────────────

resource "aws_s3_bucket" "static_assets" {
  #checkov:skip=CKV2_AWS_62:No event notifications needed — CD pipeline syncs directly
  #checkov:skip=CKV_AWS_144:Cross-region replication not needed for dev static assets
  #checkov:skip=CKV_AWS_18:Access logging requires separate logging bucket — not configured for dev
  #checkov:skip=CKV_AWS_347:force_destroy enabled for dev — must allow terraform destroy
  bucket = "cost-detective-${var.environment}-static-assets"
  force_destroy = true

  tags = {
    Name        = "cost-detective-${var.environment}-static-assets"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "static_assets" {
  bucket = aws_s3_bucket.static_assets.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "static_assets" {
  bucket = aws_s3_bucket.static_assets.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 server-side encryption — KMS managed key
resource "aws_s3_bucket_server_side_encryption_configuration" "static_assets" {
  bucket = aws_s3_bucket.static_assets.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

# S3 lifecycle — expire noncurrent versions after 30 days
resource "aws_s3_bucket_lifecycle_configuration" "static_assets" {
  bucket = aws_s3_bucket.static_assets.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# ─── ACM Certificate (disabled — no domain yet) ────────────────────
# Uncomment and set route53_zone_id + domain_name in tfvars when ready

# ─── WAF Web ACL ───────────────────────────────────────────────────

resource "aws_wafv2_web_acl" "main" {
  #checkov:skip=CKV2_AWS_31:WAF logging requires Firehose — not configured for dev
  name        = "cost-detective-${var.environment}"
  description = "WAF ACL for AI Cost Detective - rate limiting + OWASP protection"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "CostDetectiveWAF"
    sampled_requests_enabled   = true
  }

  # Rate-based rule — block IPs exceeding 2000 requests in 5 minutes
  rule {
    name     = "rate-limiting"
    priority = 0

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimitRule"
      sampled_requests_enabled   = true
    }
  }

  # SQL injection prevention
  rule {
    name     = "sqli-prevention"
    priority = 1

    action {
      block {}
    }

    statement {
      sqli_match_statement {
        field_to_match {
          query_string {}
        }
        text_transformation {
          priority = 0
          type     = "URL_DECODE"
        }
        text_transformation {
          priority = 1
          type     = "HTML_ENTITY_DECODE"
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "SQLiRule"
      sampled_requests_enabled   = true
    }
  }

  # Cross-site scripting prevention
  rule {
    name     = "xss-prevention"
    priority = 2

    action {
      block {}
    }

    statement {
      xss_match_statement {
        field_to_match {
          body {}
        }
        text_transformation {
          priority = 0
          type     = "URL_DECODE"
        }
        text_transformation {
          priority = 1
          type     = "HTML_ENTITY_DECODE"
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "XSSRule"
      sampled_requests_enabled   = true
    }
  }

  # AWS managed rules — common vulnerabilities
  rule {
    name     = "aws-managed-common"
    priority = 3

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"

        # Exclude bad inputs body size rule (may block valid uploads)
        rule_action_override {
          name = "SizeRestrictions_BODY"
          action_to_use {
            count {}
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedCommonRule"
      sampled_requests_enabled   = true
    }
  }

  # AWS managed rules — known bad IPs
  rule {
    name     = "aws-managed-bad-ips"
    priority = 4

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedBadInputsRule"
      sampled_requests_enabled   = true
    }
  }

  tags = {
    Name        = "cost-detective-${var.environment}"
    Environment = var.environment
  }
}

# ─── ArgoCD GitOps Layer ───────────────────────────────────────────

module "argocd" {
  source                             = "../../modules/argocd"
  environment                        = var.environment
  cluster_endpoint                   = module.eks.cluster_endpoint
  cluster_certificate_authority_data = module.eks.cluster_certificate_authority_data
  cluster_id                         = module.eks.cluster_id
}

# ─── Log Analysis Lambda ──────────────────────────────────────────

module "log_analysis" {
  source      = "../../modules/log-analysis"
  environment = var.environment
  source_dir  = "../../../lambda/log-analysis"
  log_groups  = "/aws/eks/cost-detective/cluster,/aws/rds/cost-detective/error,/aws/lambda/log-analysis-${var.environment}"

  slack_webhook_url = var.slack_webhook_url
  ses_from_email    = var.ses_from_email
  ses_to_email      = var.ses_to_email
}
