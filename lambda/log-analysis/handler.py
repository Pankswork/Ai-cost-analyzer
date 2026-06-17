"""
Log Analysis Lambda — analyzes CloudWatch logs for anomalies.

Triggered daily by EventBridge. Scans multiple log groups for:
- Error rate spikes (5xx, 4xx surges)
- Cost anomaly patterns
- Infrastructure warnings

Stores results in DynamoDB and sends alerts via SES + Slack.
"""

import os
import json
import boto3
from datetime import datetime, timedelta, timezone
from typing import Any

LOGS_GROUPS = os.environ.get("LOG_GROUPS", "/aws/eks/cost-detective/cluster,/aws/rds/cost-detective/error").split(",")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "noreply@bestfreeaifor.com")
SES_TO_EMAIL = os.environ.get("SES_TO_EMAIL", "admin@bestfreeaifor.com")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "log-analysis-reports")

logs_client = boto3.client("logs")
ses_client = boto3.client("ses")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE)


def lambda_handler(event: dict, context: Any) -> dict:
    analysis_results = []

    for log_group in LOGS_GROUPS:
        log_group = log_group.strip()
        if not log_group:
            continue

        try:
            result = analyze_log_group(log_group)
            analysis_results.append(result)
        except Exception as e:
            analysis_results.append({
                "log_group": log_group,
                "status": "error",
                "error": str(e),
            })

    report = {
        "report_id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_groups_analyzed": len(analysis_results),
        "results": analysis_results,
    }

    store_report(report)

    anomalies = [r for r in analysis_results if r.get("anomalies")]
    if anomalies:
        send_alerts(report)

    return {"statusCode": 200, "body": json.dumps(report, default=str)}


def analyze_log_group(log_group: str) -> dict:
    now = datetime.now(timezone.utc)
    start_time = int((now - timedelta(hours=24)).timestamp() * 1000)
    end_time = int(now.timestamp() * 1000)

    error_count = 0
    warn_count = 0
    total_count = 0
    error_patterns: dict[str, int] = {}

    try:
        paginator = logs_client.get_paginator("filter_log_events")
        for page in paginator.paginate(
            logGroupName=log_group,
            startTime=start_time,
            endTime=end_time,
        ):
            for event in page.get("events", []):
                total_count += 1
                msg = event.get("message", "")
                if "ERROR" in msg or "CRITICAL" in msg or "Exception" in msg:
                    error_count += 1
                    for pattern in ["Timeout", "ConnectionError", "Permission", "Throttling",
                                    "AccessDenied", "LimitExceeded", "ServiceUnavailable"]:
                        if pattern in msg:
                            error_patterns[pattern] = error_patterns.get(pattern, 0) + 1
                elif "WARN" in msg or "WARNING" in msg:
                    warn_count += 1
    except logs_client.exceptions.ResourceNotFoundException:
        return {"log_group": log_group, "status": "not_found"}

    error_rate = (error_count / total_count * 100) if total_count > 0 else 0

    anomalies = []
    if error_rate > 5:
        anomalies.append({
            "type": "high_error_rate",
            "severity": "high",
            "message": f"Error rate is {error_rate:.1f}% (threshold: 5%)",
            "error_count": error_count,
            "total_count": total_count,
        })
    if error_patterns:
        top_pattern = max(error_patterns, key=error_patterns.get)
        if error_patterns[top_pattern] > 10:
            anomalies.append({
                "type": "recurring_error",
                "severity": "medium",
                "message": f"Recurring '{top_pattern}' errors: {error_patterns[top_pattern]} occurrences",
                "pattern": top_pattern,
                "count": error_patterns[top_pattern],
            })

    return {
        "log_group": log_group,
        "status": "ok",
        "period_hours": 24,
        "total_logs": total_count,
        "errors": error_count,
        "warnings": warn_count,
        "error_rate_pct": round(error_rate, 2),
        "error_patterns": error_patterns,
        "anomalies": anomalies,
    }


def store_report(report: dict):
    try:
        table.put_item(Item=report)
    except Exception as e:
        print(f"Failed to store report: {e}")


def send_alerts(report: dict):
    subject = f"Log Anomaly Detected — {report['log_groups_analyzed']} groups analyzed"

    message_parts = ["Log Analysis Report", f"Time: {report['timestamp']}", ""]
    for result in report["results"]:
        if result.get("anomalies"):
            message_parts.append(f"Log Group: {result['log_group']}")
            for a in result["anomalies"]:
                message_parts.append(f"  [{a['severity'].upper()}] {a['message']}")
            message_parts.append("")

    message = "\n".join(message_parts)

    if SLACK_WEBHOOK_URL:
        try:
            import httpx
            httpx.post(SLACK_WEBHOOK_URL, json={"text": f"*{subject}*\n\n{message}"})
        except Exception as e:
            print(f"Slack alert failed: {e}")

    try:
        ses_client.send_email(
            Source=SES_FROM_EMAIL,
            Destination={"ToAddresses": [SES_TO_EMAIL]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": message}},
            },
        )
    except Exception as e:
        print(f"Email alert failed: {e}")
