data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.module}/secret-rotation.zip"
}

resource "aws_iam_role" "rotation_lambda" {
  name = "cost-detective-${var.environment}-secret-rotation"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "rotation_lambda" {
  name = "cost-detective-${var.environment}-secret-rotation-policy"
  role = aws_iam_role.rotation_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:PutSecretValue",
          "secretsmanager:DescribeSecret",
          "secretsmanager:UpdateSecretVersionStage",
        ]
        Resource = var.secret_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/secret-rotation-${var.environment}:*"
      },
    ]
  })
}

# checkov:skip=CKV_AWS_117:Lambda reads secrets via API — no VPC needed
# checkov:skip=CKV_AWS_272:Code signing not required for internal Lambda
resource "aws_lambda_function" "rotation" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "secret-rotation-${var.environment}"
  role             = aws_iam_role.rotation_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 128
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  tags = {
    Name        = "secret-rotation-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_lambda_permission" "secretsmanager" {
  statement_id  = "AllowSecretsManagerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rotation.function_name
  principal     = "secretsmanager.amazonaws.com"
  source_arn    = var.secret_arn
}

resource "aws_secretsmanager_secret_rotation" "backend" {
  secret_id           = var.secret_arn
  rotation_lambda_arn = aws_lambda_function.rotation.arn

  rotation_rules {
    automatically_after_days = 30
  }
}
