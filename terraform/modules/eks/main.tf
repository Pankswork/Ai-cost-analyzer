# EKS Cluster Module
#
# Creates an Amazon EKS cluster with:
# - Managed node group (m7i-flex.large via free tier)
# - IRSA (IAM Roles for Service Accounts) enabled
# - Control plane logging enabled for all log types
# - Cluster autoscaler support
#
# Uses the official AWS EKS Terraform module for best practices

data "aws_caller_identity" "current" {}

module "eks" {
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-eks.git?ref=v21.20.0"

  name               = "cost-detective-${var.environment}"
  kubernetes_version = var.cluster_version
  region             = var.aws_region

  # VPC configuration
  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  # Control plane access — public for kubectl, private for internal traffic
  endpoint_public_access  = true
  endpoint_private_access = true

  # Enable all control plane log types for full observability
  # Cost: ~$0.50/log-stream/day — cheap for dev observability
  enabled_log_types = [
    "api",
    "audit",
    "authenticator",
    "controllerManager",
    "scheduler",
  ]

  # Managed node group — single m7i-flex.large (free tier eligible)
  # In production, separate node groups for system vs. application workloads
  eks_managed_node_groups = {
    cost-detective = {
      create = true

      desired_size = 1
      min_size     = 1
      max_size     = 3

      instance_types = ["m7i-flex.large", "c7i-flex.large"]

      # EBS optimization — gp3 with encryption by default
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 20
            volume_type           = "gp3"
            encrypted             = true
            delete_on_termination = true
          }
        }
      }

      tags = {
        Environment = var.environment
        # Required tag for cluster autoscaler auto-discovery
        "k8s.io/cluster-autoscaler/enabled" = "true"
      }
    }
  }

  # Enable IRSA — IAM Roles for Service Accounts
  # Each pod gets its own IAM role. No static keys, no node-level permissions.
  enable_cluster_creator_admin_permissions = true

  # Grant the account root user admin access (for console/kubectl locally)
  access_entries = {
    root = {
      kubernetes_groups = []
      principal_arn     = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
      policy_associations = {
        admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  }

  # Required addons for the cluster to function
  addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent    = true
      before_compute = true
    }
  }

  enable_irsa = true

  tags = {
    Environment = var.environment
  }
}

# ─── IAM Role for Backend Service Account (IRSA) ─────────────────
#
# The FastAPI backend gets its own IAM role with minimal permissions.
# This follows the principle of least privilege — the backend can
# only read AWS resources, nothing else.

resource "aws_iam_role" "backend" {
  name = "cost-detective-${var.environment}-backend"

  # Trust policy — allows the Kubernetes service account to assume this role
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${module.eks.oidc_provider}:sub" : "system:serviceaccount:cost-detective:backend"
          }
        }
      }
    ]
  })
}

# ─── IAM Role for ALB Controller (IRSA) ──────────────────────────

resource "aws_iam_role" "alb_controller" {
  name = "cost-detective-${var.environment}-alb-controller"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${module.eks.oidc_provider}:sub" : "system:serviceaccount:kube-system:aws-load-balancer-controller"
          }
        }
      }
    ]
  })
}

# checkov:skip=CKV_AWS_289:ALB controller needs ec2, elb, waf, acm, iam and shield permissions with wildcard resources to dynamically manage load balancer infrastructure
resource "aws_iam_role_policy" "alb_controller" {
  name = "cost-detective-${var.environment}-alb-controller-policy"
  role = aws_iam_role.alb_controller.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "acm:DescribeCertificate",
          "acm:ListCertificates",
          "acm:GetCertificate"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:CreateSecurityGroup",
          "ec2:CreateTags",
          "ec2:DeleteSecurityGroup",
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeSubnets",
          "ec2:DescribeTags",
          "ec2:DescribeVpcs",
          "ec2:RevokeSecurityGroupIngress"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:AddListenerCertificates",
          "elasticloadbalancing:AddTags",
          "elasticloadbalancing:CreateListener",
          "elasticloadbalancing:CreateLoadBalancer",
          "elasticloadbalancing:CreateRule",
          "elasticloadbalancing:CreateTargetGroup",
          "elasticloadbalancing:DeleteListener",
          "elasticloadbalancing:DeleteLoadBalancer",
          "elasticloadbalancing:DeleteRule",
          "elasticloadbalancing:DeleteTargetGroup",
          "elasticloadbalancing:DeregisterTargets",
          "elasticloadbalancing:DescribeListenerCertificates",
          "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:DescribeLoadBalancerAttributes",
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeRules",
          "elasticloadbalancing:DescribeSSLPolicies",
          "elasticloadbalancing:DescribeTags",
          "elasticloadbalancing:DescribeListenerAttributes",
          "elasticloadbalancing:DescribeTargetGroupAttributes",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth",
          "elasticloadbalancing:ModifyListener",
          "elasticloadbalancing:ModifyLoadBalancerAttributes",
          "elasticloadbalancing:ModifyRule",
          "elasticloadbalancing:ModifyTargetGroup",
          "elasticloadbalancing:ModifyTargetGroupAttributes",
          "elasticloadbalancing:RegisterTargets",
          "elasticloadbalancing:RemoveListenerCertificates",
          "elasticloadbalancing:RemoveTags",
          "elasticloadbalancing:SetIpAddressType",
          "elasticloadbalancing:SetSecurityGroups",
          "elasticloadbalancing:SetSubnets",
          "elasticloadbalancing:SetWebACL"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:CreateServiceLinkedRole",
          "iam:GetServerCertificate",
          "iam:ListServerCertificates"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:DescribeUserPoolClient"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "waf-regional:GetWebACLForResource",
          "waf-regional:GetWebACL",
          "waf-regional:AssociateWebACL",
          "waf-regional:DisassociateWebACL"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "tag:GetResources",
          "tag:TagResources"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "wafv2:GetWebACL",
          "wafv2:GetWebACLForResource",
          "wafv2:AssociateWebACL",
          "wafv2:DisassociateWebACL"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "shield:DescribeSubscription",
          "shield:ListAttacks"
        ]
        Resource = "*"
      }
    ]
  })
}

# checkov:skip=CKV_AWS_355:Describe actions require * resource — ARNs unknown before discovery
# checkov:skip=CKV_AWS_290:Read-only Describe actions, no write access
resource "aws_iam_role_policy" "backend" {
  name = "cost-detective-${var.environment}-backend-policy"
  role = aws_iam_role.backend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          "ec2:DescribeAddresses",
          "ec2:DescribeSnapshots",
          "rds:DescribeDBInstances",
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeTargetGroups",
          "s3:ListAllMyBuckets",
          "tag:GetResources",
        ]
        Resource = "*"
      }
    ]
  })
}

# ─── IAM Role for External Secrets Operator (IRSA) ──────────────
#
# Allows the External Secrets Operator (deployed in the external-secrets
# namespace) to read secrets from AWS Secrets Manager.  The
# ClusterSecretStore uses serviceAccountRef to point here.

resource "aws_iam_role" "external_secrets" {
  name = "cost-detective-${var.environment}-external-secrets"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${module.eks.oidc_provider}:sub" : "system:serviceaccount:external-secrets:external-secrets"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "external_secrets" {
  name = "cost-detective-${var.environment}-external-secrets-policy"
  role = aws_iam_role.external_secrets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = "*"
      }
    ]
  })
}


