# RDS PostgreSQL Module
#
# Creates a managed PostgreSQL instance for the application database.
# The database is:
# - Deployed in private subnets (no public access)
# - Only accessible from the EKS cluster security group
# - Encrypted at rest (AWS-managed key)
# - Backed up automatically with 7-day retention

data "aws_caller_identity" "current" {}

# Random password for the database
resource "random_password" "db_password" {
  length  = 24
  special = false
}

# DB subnet group — places RDS in private subnets
resource "aws_db_subnet_group" "main" {
  name       = "cost-detective-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "cost-detective-${var.environment}"
  }
}

# Security group — only allows PostgreSQL from EKS cluster
resource "aws_security_group" "rds" {
  name        = "cost-detective-${var.environment}-rds"
  description = "RDS PostgreSQL security group"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.cluster_security_group_id]
    description     = "PostgreSQL from EKS cluster"
  }

  tags = {
    Name = "cost-detective-${var.environment}-rds"
  }
}

# IAM role for RDS Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  name = "cost-detective-${var.environment}-rds-monitoring"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "monitoring.rds.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Name = "cost-detective-${var.environment}-rds-monitoring"
  }
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# KMS key for RDS Performance Insights encryption
resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS Performance Insights"
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
    Name = "cost-detective-${var.environment}-rds"
  }
}

resource "aws_kms_alias" "rds" {
  name          = "alias/cost-detective-${var.environment}-rds"
  target_key_id = aws_kms_key.rds.id
}

# DB parameter group — enables PostgreSQL query logging
resource "aws_db_parameter_group" "main" {
  name        = "cost-detective-${var.environment}"
  family      = "postgres16"
  description = "Custom parameter group for cost-detective-${var.environment}"

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "0"
  }

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = {
    Name = "cost-detective-${var.environment}"
  }
}

resource "aws_db_instance" "main" {
  #checkov:skip=CKV_AWS_157:Single-AZ is sufficient for dev — Multi-AZ adds unnecessary cost
  #checkov:skip=CKV_AWS_118:Enhanced monitoring disabled for dev — free tier constraint
  identifier = "cost-detective-${var.environment}"

  # Engine configuration
  engine                     = "postgres"
  engine_version             = "16.14"
  instance_class             = var.instance_class
  auto_minor_version_upgrade = true
  parameter_group_name       = aws_db_parameter_group.main.name

  # Database configuration
  db_name  = var.database_name
  username = "cost_detective"
  password = random_password.db_password.result

  # Storage — gp3 with encryption
  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  # Network — private subnets only
  db_subnet_group_name                = aws_db_subnet_group.main.name
  vpc_security_group_ids              = [aws_security_group.rds.id]
  publicly_accessible                 = false
  iam_database_authentication_enabled = true

  # Backups — 1-day retention (free tier limit)
  backup_retention_period = 1
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  # Enhanced Monitoring — disabled (free tier, adds cost)
  monitoring_interval = 0

  # Performance Insights — encrypted with KMS CMK, 7-day retention (free tier)
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  performance_insights_kms_key_id       = aws_kms_key.rds.arn

  # Logging — PostgreSQL logs to CloudWatch
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  # Copy tags to snapshots
  copy_tags_to_snapshot = true

  # Deletion protection — disabled for dev so terraform destroy works
  #checkov:skip=CKV_AWS_292:Disabled intentionally — dev env, must be able to destroy/recreate
  deletion_protection = false
  skip_final_snapshot = true

  tags = {
    Name = "cost-detective-${var.environment}"
  }
}
