output "lambda_function_name" {
  description = "Name of the log analysis Lambda function"
  value       = aws_lambda_function.log_analysis.function_name
}

output "lambda_function_arn" {
  description = "ARN of the log analysis Lambda function"
  value       = aws_lambda_function.log_analysis.arn
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table for log reports"
  value       = aws_dynamodb_table.log_reports.name
}
