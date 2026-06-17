data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# KMS key for DynamoDB and Lambda encryption
resource "aws_kms_key" "log_analysis" {
  description             = "KMS key for log analysis DynamoDB and Lambda"
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
    Name        = "log-analysis-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "log_analysis" {
  name          = "alias/log-analysis-${var.environment}"
  target_key_id = aws_kms_key.log_analysis.id
}

resource "aws_dynamodb_table" "log_reports" {
  name         = "log-analysis-reports-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "report_id"

  attribute {
    name = "report_id"
    type = "S"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.log_analysis.arn
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name        = "log-analysis-reports-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_iam_role" "lambda_role" {
  name = "log-analysis-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Name        = "log-analysis-${var.environment}"
    Environment = var.environment
  }
}

# checkov:skip=CKV_AWS_355:SES actions require * resource for verified identities
resource "aws_iam_role_policy" "lambda_policy" {
  name = "log-analysis-${var.environment}"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:FilterLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/eks/*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = aws_dynamodb_table.log_reports.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail",
        ]
        Resource = "arn:aws:ses:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:identity/*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/log-analysis-${var.environment}:*"
      },
    ]
  })
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.module}/log-analysis.zip"
}

# checkov:skip=CKV_AWS_117:Lambda does not need VPC access — reads CloudWatch logs via API
# checkov:skip=CKV_AWS_116:No DLQ needed — errors logged to CloudWatch
# checkov:skip=CKV_AWS_272:Code signing not required for internal Lambda
resource "aws_lambda_function" "log_analysis" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "log-analysis-${var.environment}"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 512
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  reserved_concurrent_executions = 5

  kms_key_arn = aws_kms_key.log_analysis.arn

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      LOG_GROUPS        = var.log_groups
      SLACK_WEBHOOK_URL = var.slack_webhook_url
      SES_FROM_EMAIL    = var.ses_from_email
      SES_TO_EMAIL      = var.ses_to_email
      DYNAMODB_TABLE    = aws_dynamodb_table.log_reports.name
    }
  }

  tags = {
    Name        = "log-analysis-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "log-analysis-daily-${var.environment}"
  description         = "Daily trigger for log analysis"
  schedule_expression = "cron(0 6 * * ? *)"

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule = aws_cloudwatch_event_rule.daily.name
  arn  = aws_lambda_function.log_analysis.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.log_analysis.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily.arn
}
