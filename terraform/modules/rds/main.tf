# RDS PostgreSQL Module
#
# Creates a managed PostgreSQL instance for the application database.
# The database is:
# - Deployed in private subnets (no public access)
# - Only accessible from the EKS cluster security group
# - Encrypted at rest (AWS-managed key)
# - Backed up automatically with 7-day retention

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

# RDS PostgreSQL instance
resource "aws_db_instance" "main" {
  identifier = "cost-detective-${var.environment}"

  # Engine configuration
  engine                     = "postgres"
  engine_version             = "16.3"
  instance_class             = var.instance_class
  auto_minor_version_upgrade = true

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

  # Backups — 7-day retention for dev
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  # Performance Insights — 7-day free tier retention
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  # Deletion protection — prevents accidental deletion in production
  # Disabled for dev so we can tear down easily
  deletion_protection = false
  skip_final_snapshot = true

  tags = {
    Name = "cost-detective-${var.environment}"
  }
}
