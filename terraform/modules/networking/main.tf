# VPC — the network boundary for all resources
# Uses /16 for room across multiple AZs and services
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true # Required for EKS and RDS
  enable_dns_support   = true

  tags = {
    Name = "cost-detective-${var.environment}"
  }
}

# Default security group — deny all traffic (removes default allows)
resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "cost-detective-${var.environment}-default-sg"
  }
}

# Public subnets — for ALB and NAT Gateway
# Spread across AZs for high availability
resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "cost-detective-${var.environment}-public-${count.index}"
    Type = "public"
    # Tag required by AWS Load Balancer Controller for public ALBs
    "kubernetes.io/role/elb" = "1"
  }
}

# Private subnets — for EKS nodes, RDS, Ollama
# No public IPs, egress through NAT Gateway
resource "aws_subnet" "private" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + length(var.availability_zones))
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name = "cost-detective-${var.environment}-private-${count.index}"
    Type = "private"
    # Tag required by AWS Load Balancer Controller for internal ALBs
    "kubernetes.io/role/internal-elb" = "1"
  }
}

# Internet Gateway — enables public subnet internet access
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "cost-detective-${var.environment}"
  }
}

# Elastic IP — static IP for NAT Gateway
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "cost-detective-${var.environment}-nat"
  }
}

# NAT Gateway — enables private subnets to reach the internet
# Required for ECR pulls and Ollama model downloads
# For dev, single NAT is fine. In production, use one per AZ.
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "cost-detective-${var.environment}"
  }

  depends_on = [aws_internet_gateway.main]
}

# Public route table — routes traffic through IGW
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "cost-detective-${var.environment}-public"
  }
}

# Private route table — routes traffic through NAT Gateway
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = {
    Name = "cost-detective-${var.environment}-private"
  }
}

# Route table associations
resource "aws_route_table_association" "public" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ─── VPC Endpoints (cost optimization) ────────────────────────────
#
# S3 Gateway Endpoint — free, keeps S3 traffic within AWS network
# ECR Interface Endpoints — $0.01/hr each, but save NAT data costs
# Combined savings: ~$15-20/month

# S3 Gateway Endpoint (free)
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids = [
    aws_route_table.private.id
  ]

  tags = {
    Name = "cost-detective-${var.environment}-s3-endpoint"
  }
}

# Security Group for VPC Endpoints
resource "aws_security_group" "vpc_endpoints" {
  name        = "cost-detective-${var.environment}-vpc-endpoints"
  description = "Security group for VPC Interface Endpoints"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "HTTPS from within VPC"
  }

  tags = {
    Name = "cost-detective-${var.environment}-vpc-endpoints"
  }
}

# ECR API Endpoint — allows EKS to call ECR API
resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id             = aws_vpc.main.id
  service_name       = "com.amazonaws.${var.aws_region}.ecr.api"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.vpc_endpoints.id]

  tags = {
    Name = "cost-detective-${var.environment}-ecr-api"
  }
}

# ECR DKR Endpoint — allows EKS to pull/push Docker images
resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id             = aws_vpc.main.id
  service_name       = "com.amazonaws.${var.aws_region}.ecr.dkr"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.vpc_endpoints.id]

  tags = {
    Name = "cost-detective-${var.environment}-ecr-dkr"
  }
}

# ─── VPC Flow Logs ────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

# KMS key for VPC flow log encryption
resource "aws_kms_key" "flow_logs" {
  description             = "KMS key for VPC flow log encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
    ]
  })

  tags = {
    Name        = "cost-detective-${var.environment}-flow-logs"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "flow_logs" {
  name          = "alias/cost-detective-${var.environment}-flow-logs"
  target_key_id = aws_kms_key.flow_logs.id
}

# CloudWatch log group for VPC flow logs — encrypted with KMS
resource "aws_cloudwatch_log_group" "flow_logs" {
  name              = "/aws/vpc/flow-logs/cost-detective-${var.environment}"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.flow_logs.arn

  tags = {
    Name        = "cost-detective-${var.environment}-flow-logs"
    Environment = var.environment
  }
}

# IAM role for VPC Flow Logs
resource "aws_iam_role" "flow_logs" {
  name = "cost-detective-${var.environment}-vpc-flow-logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "vpc-flow-logs.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
    ]
  })

  tags = {
    Name        = "cost-detective-${var.environment}-vpc-flow-logs"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "flow_logs" {
  role       = aws_iam_role.flow_logs.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

# VPC Flow Log — captures all traffic metadata
resource "aws_flow_log" "main" {
  iam_role_arn    = aws_iam_role.flow_logs.arn
  log_destination = aws_cloudwatch_log_group.flow_logs.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.main.id

  tags = {
    Name        = "cost-detective-${var.environment}-flow-logs"
    Environment = var.environment
  }
}
