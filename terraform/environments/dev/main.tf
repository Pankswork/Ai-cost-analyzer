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

variable "zen_api_key" {
  description = "API key for opencode Zen (AI analysis)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "admin_emails" {
  description = "Comma-separated emails that auto-become admin on registration"
  type        = string
  default     = ""
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
    },
    {
      name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
      value = module.eks.external_secrets_role_arn
    },
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
      additionalDataSources:
        - name: Loki
          type: loki
          access: proxy
          url: http://loki:3100
          isDefault: false
        - name: Tempo
          type: tempo
          access: proxy
          url: http://tempo:3100
          isDefault: false
      dashboardProviders:
        dashboardproviders.yaml:
          apiVersion: 1
          providers:
            - name: default
              orgId: 1
              folder: ""
              type: file
              disableDeletion: false
              editable: true
              options:
                path: /var/lib/grafana/dashboards/default
      dashboards:
        default:
          application-overview:
            gnetId: null
            revision: 1
            datasource: Prometheus
            json: |
              {
                "title": "Application Overview",
                "uid": "app-overview",
                "version": 1,
                "panels": [
                  {
                    "title": "Request Rate",
                    "type": "graph",
                    "gridPos": {"x": 0, "y": 0, "w": 8, "h": 8},
                    "targets": [{
                      "expr": "rate(http_requests_total{job='backend'}[5m])",
                      "legendFormat": "{{status_code}}"
                    }]
                  },
                  {
                    "title": "P99 Latency",
                    "type": "graph",
                    "gridPos": {"x": 8, "y": 0, "w": 8, "h": 8},
                    "targets": [{
                      "expr": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{job='backend'}[5m]))",
                      "legendFormat": "{{method}} {{route}}"
                    }]
                  },
                  {
                    "title": "Error Rate",
                    "type": "graph",
                    "gridPos": {"x": 16, "y": 0, "w": 8, "h": 8},
                    "targets": [{
                      "expr": "rate(http_requests_total{job='backend',status_code=~'5..'}[5m]) / rate(http_requests_total{job='backend'}[5m])",
                      "legendFormat": "error ratio"
                    }]
                  },
                  {
                    "title": "Active Scans",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 8, "w": 4, "h": 4},
                    "targets": [{
                      "expr": "increase(scans_initiated_total[24h])"
                    }]
                  },
                  {
                    "title": "Savings Found",
                    "type": "stat",
                    "gridPos": {"x": 4, "y": 8, "w": 4, "h": 4},
                    "targets": [{
                      "expr": "sum(increase(savings_found_total[24h]))"
                    }]
                  },
                  {
                    "title": "Pod CPU Usage",
                    "type": "graph",
                    "gridPos": {"x": 8, "y": 8, "w": 8, "h": 8},
                    "targets": [{
                      "expr": "sum(rate(container_cpu_usage_seconds_total{namespace='cost-detective',pod=~'backend-.*'}[5m])) by (pod)",
                      "legendFormat": "{{pod}}"
                    }]
                  }
                ]
              }
          business-metrics:
            gnetId: null
            revision: 1
            datasource: Prometheus
            json: |
              {
                "title": "Business Metrics",
                "uid": "business-metrics",
                "version": 1,
                "panels": [
                  {
                    "title": "Scans per Day",
                    "type": "bargauge",
                    "gridPos": {"x": 0, "y": 0, "w": 6, "h": 6},
                    "targets": [{
                      "expr": "increase(scans_initiated_total[24h])"
                    }]
                  },
                  {
                    "title": "AI Analysis Duration (p95)",
                    "type": "graph",
                    "gridPos": {"x": 6, "y": 0, "w": 6, "h": 6},
                    "targets": [{
                      "expr": "histogram_quantile(0.95, rate(analysis_duration_seconds_bucket[5m]))",
                      "legendFormat": "p95"
                    }]
                  },
                  {
                    "title": "Resources Scanned by Type",
                    "type": "piechart",
                    "gridPos": {"x": 12, "y": 0, "w": 6, "h": 6},
                    "targets": [{
                      "expr": "sum(resources_scanned_total) by (resource_type)",
                      "legendFormat": "{{resource_type}}"
                    }]
                  },
                  {
                    "title": "Recommendations Generated",
                    "type": "stat",
                    "gridPos": {"x": 18, "y": 0, "w": 6, "h": 6},
                    "targets": [{
                      "expr": "increase(recommendations_generated_total[24h])"
                    }]
                  }
                ]
              }
          tracing:
            gnetId: null
            revision: 1
            datasource: Tempo
            json: |
              {
                "title": "Tracing",
                "uid": "tracing",
                "version": 1,
                "panels": [
                  {
                    "title": "Trace Search",
                    "type": "tempo",
                    "gridPos": {"x": 0, "y": 0, "w": 24, "h": 12},
                    "datasource": "Tempo"
                  },
                  {
                    "title": "Service Graph",
                    "type": "tempo-service-graph",
                    "gridPos": {"x": 0, "y": 12, "w": 24, "h": 12},
                    "datasource": "Tempo"
                  }
                ]
              }
    prometheus:
      prometheusSpec:
        retention: 7d
        resources:
          requests:
            cpu: "500m"
            memory: "2Gi"
        ruleSelectorNilUsesHelmValues: false
        serviceMonitorSelectorNilUsesHelmValues: false
    alertmanager:
      config:
        global:
          slack_api_url: "${var.slack_webhook_url}"
        route:
          receiver: default
          repeatInterval: 4h
          routes:
            - match:
                severity: critical
              receiver: critical
              repeatInterval: 1h
        receivers:
          - name: default
            slack_configs:
              - channel: "#alerts"
                title: "{{ .GroupLabels.alertname }}"
                text: "{{ .CommonAnnotations.summary }}"
          - name: critical
            slack_configs:
              - channel: "#alerts-critical"
                title: "[CRITICAL] {{ .GroupLabels.alertname }}"
                text: "{{ .CommonAnnotations.summary }}"
    YAML
  ]

  depends_on = [module.eks]
}

# ─── Tempo (Distributed Tracing) ──────────────────────────────────
resource "helm_release" "tempo" {
  name       = "tempo"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "tempo"
  version    = "1.10.3"
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name
  timeout    = 600

  values = [
    <<-YAML
    tempo:
      retention: 168h
      storage:
        trace:
          backend: local
          local:
            path: /var/tempo/traces
          wal:
            path: /var/tempo/wal
    ingester:
      trace_idle_period: 10s
      max_block_duration: 5m
    querier:
      frontend_worker:
        frontend_address: tempo-tempo-query-frontend:9095
    metricsGenerator:
      enabled: true
    storage:
      trace:
        backend: local
    compactor:
      compaction:
        block_retention: 168h
    persistence:
      enabled: true
      storageClassName: gp2
      size: 5Gi
    serviceAccount:
      create: true
    YAML
  ]

  depends_on = [module.eks]
}

# ─── OpenTelemetry Collector (Gateway) ────────────────────────────
resource "helm_release" "otel_collector" {
  name       = "otel-collector"
  repository = "https://open-telemetry.github.io/opentelemetry-helm-charts"
  chart      = "opentelemetry-collector"
  version    = "0.105.0"
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name

  values = [
    <<-YAML
    mode: deployment
    replicaCount: 1
    image:
      repository: otel/opentelemetry-collector-contrib
      tag: 0.112.0
    config:
      receivers:
        otlp:
          protocols:
            grpc:
              endpoint: 0.0.0.0:4317
            http:
              endpoint: 0.0.0.0:4318
      processors:
        batch:
          timeout: 1s
          send_batch_size: 1024
        memory_limiter:
          check_interval: 5s
          limit_mib: 512
          spike_limit_mib: 128
      exporters:
        otlp/tempo:
          endpoint: tempo:4317
          tls:
            insecure: true
        prometheus:
          endpoint: 0.0.0.0:8889
          resource_to_telemetry_conversion:
            enabled: true
        loki:
          endpoint: http://loki:3100/loki/api/v1/push
          tls:
            insecure: true
      service:
        pipelines:
          traces:
            receivers: [otlp]
            processors: [memory_limiter, batch]
            exporters: [otlp/tempo]
          metrics:
            receivers: [otlp]
            processors: [memory_limiter, batch]
            exporters: [prometheus]
          logs:
            receivers: [otlp]
            processors: [memory_limiter, batch]
            exporters: [loki]
    service:
      enabled: true
      type: ClusterIP
      ports:
        - name: otlp-grpc
          port: 4317
          targetPort: 4317
          protocol: TCP
        - name: otlp-http
          port: 4318
          targetPort: 4318
          protocol: TCP
        - name: prometheus
          port: 8889
          targetPort: 8889
          protocol: TCP
    serviceMonitor:
      enabled: true
      endpoints:
        - port: prometheus
          interval: 15s
          path: /metrics
    resources:
      requests:
        cpu: 100m
        memory: 256Mi
      limits:
        cpu: 500m
        memory: 512Mi
    YAML
  ]

  depends_on = [helm_release.tempo, helm_release.loki, module.eks]
}

# ─── Loki (Log Aggregation) ────────────────────────────────────────
resource "helm_release" "loki" {
  name       = "loki"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "loki"
  version    = "6.27.0"
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name

  values = [
    <<-YAML
    deploymentMode: SingleBinary
    loki:
      commonConfig:
        replication_factor: 1
      storage:
        type: filesystem
      schemaConfig:
        configs:
          - from: 2024-01-01
            store: tsdb
            object_store: filesystem
            schema: v13
            index:
              prefix: loki_index_
              period: 24h
    singleBinary:
      replicas: 1
      persistence:
        enabled: true
        storageClass: gp2
        size: 10Gi
    backend:
      replicas: 0
    read:
      replicas: 0
    write:
      replicas: 0
    chunksCache:
      enabled: false
    resultsCache:
      enabled: false
    gateway:
      enabled: false
    YAML
  ]

  depends_on = [module.eks]
}

# ─── Promtail (Log Agent DaemonSet) ────────────────────────────────
resource "helm_release" "promtail" {
  name       = "promtail"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "promtail"
  version    = "6.16.5"
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name

  values = [
    <<-YAML
    config:
      clients:
        - url: http://loki:3100/loki/api/v1/push
    YAML
  ]

  depends_on = [helm_release.loki, module.eks]
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

  backend_secret_arn = aws_secretsmanager_secret.backend.arn

  depends_on = [module.networking]
}

# ─── RDS Database Layer ────────────────────────────────────────────

module "rds" {
  source                    = "../../modules/rds"
  environment               = var.environment
  vpc_id                    = module.networking.vpc_id
  private_subnet_ids        = module.networking.private_subnet_ids
  cluster_security_group_id = module.eks.cluster_security_group_id
  node_security_group_id    = module.eks.node_security_group_id

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
  bucket        = "cost-detective-${var.environment}-static-assets"
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

# ─── Backend Secrets (AWS Secrets Manager) ─────────────────────────
#
# The backend reads these at startup via External Secrets Operator.
# Terraform creates the secret so it exists before the app starts.

resource "random_password" "jwt_secret" {
  length  = 32
  special = false
}

resource "random_password" "admin_api_key" {
  length  = 32
  special = false
}

# checkov:skip=CKV_AWS_149:Dev environment on AWS Free Tier — default AWS-managed key costs $0 vs $1/month for CMK
resource "aws_secretsmanager_secret" "backend" {
  name = "cost-detective-${var.environment}-backend"
}

resource "aws_secretsmanager_secret_version" "backend" {
  secret_id = aws_secretsmanager_secret.backend.id
  secret_string = jsonencode({
    jwt_secret_key = random_password.jwt_secret.result
    database_url   = "postgresql+asyncpg://${module.rds.db_username}:${module.rds.db_password}@${module.rds.db_endpoint}/${module.rds.db_name}"
    zen_api_key    = var.zen_api_key
    admin_api_key  = random_password.admin_api_key.result
    admin_emails   = var.admin_emails
    sentry_dsn     = ""
  })

  depends_on = [module.rds]
}

# ─── Secret Rotation ────────────────────────────────────────────────
#
# Rotates the jwt_secret_key every 30 days via a Lambda function.
# The database_url and zen_api_key fields are preserved as-is.

module "secret_rotation" {
  source      = "../../modules/secret-rotation"
  environment = var.environment
  secret_arn  = aws_secretsmanager_secret.backend.arn
  source_dir  = "../../../lambda/secret-rotation"

  depends_on = [module.eks]
}

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

# ─── Namespace & Ingress ───────────────────────────────────────────

resource "kubernetes_namespace_v1" "cost_detective" {
  depends_on = [module.eks]
  metadata {
    name = "cost-detective"
    labels = {
      name                            = "cost-detective"
      environment                     = "dev"
      "argocd.argoproj.io/managed-by" = "argocd"
    }
  }
}

resource "kubernetes_ingress_v1" "main" {
  depends_on = [kubernetes_namespace_v1.cost_detective]
  metadata {
    name      = "cost-detective"
    namespace = kubernetes_namespace_v1.cost_detective.metadata[0].name
    annotations = {
      "kubernetes.io/ingress.class"                = "alb"
      "alb.ingress.kubernetes.io/scheme"           = "internet-facing"
      "alb.ingress.kubernetes.io/target-type"      = "ip"
      "alb.ingress.kubernetes.io/healthcheck-path" = "/api/health"
      "alb.ingress.kubernetes.io/success-codes"    = "200"
      "alb.ingress.kubernetes.io/waf-acl-arn"      = aws_wafv2_web_acl.main.arn
    }
  }
  spec {
    rule {
      http {
        path {
          path      = "/api"
          path_type = "Prefix"
          backend {
            service {
              name = "backend"
              port {
                number = 8000
              }
            }
          }
        }
        path {
          path      = "/ws"
          path_type = "Prefix"
          backend {
            service {
              name = "backend"
              port {
                number = 8000
              }
            }
          }
        }
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = "frontend"
              port {
                number = 80
              }
            }
          }
        }
      }
    }
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
