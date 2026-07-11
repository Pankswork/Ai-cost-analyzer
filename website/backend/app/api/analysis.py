import uuid
import json
from datetime import datetime, timezone
import structlog
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from opentelemetry import trace
from app.db.session import get_db
from app.models.misc import CostReport
from app.models.user import User
from app.models.pydantic_models import AnalysisTriggerRequest, AnalysisRunResponse, CostReportResponse, CostReportDetailResponse
from app.config import settings
from app.middleware.auth_middleware import get_admin_user, get_current_user
from app.core.telemetry import get_tracer

logger = structlog.get_logger(__name__)
_tracer = get_tracer()

router = APIRouter(tags=["analysis"])


async def _run_cost_analysis(db: AsyncSession, triggered_by: str = "manual") -> CostReport:
    report_uuid = str(uuid.uuid4())
    report = CostReport(
        report_uuid=report_uuid,
        aws_account_id=settings.aws_account_id,
        aws_region=settings.aws_region,
        status="running",
        triggered_by=triggered_by,
    )
    db.add(report)
    await db.commit()

    with _tracer.start_as_current_span("cost_analysis_run") as span:
        span.set_attribute("report_uuid", report_uuid)
        span.set_attribute("triggered_by", triggered_by)
        try:
            from app.services.aws_scanner import AwsResourceScanner
            from app.services.ai_analyzer import AiAnalyzer

            scanner = AwsResourceScanner()
            analyzer = AiAnalyzer()

            resources = await scanner.scan_resources()
            span.set_attribute("resources_found", len(resources))
            recommendations = await analyzer.analyze(resources)
            span.set_attribute("recommendations_count", len(recommendations))

            total_savings = sum(r.get("estimated_monthly_savings", 0) for r in recommendations)
            span.set_attribute("total_estimated_savings", total_savings)

            report.status = "completed"
            report.total_resources = len(resources)
            report.total_recommendations = len(recommendations)
            report.total_estimated_savings = total_savings
            report.resources = json.dumps(resources)
            report.recommendations = json.dumps(recommendations)
            report.completed_at = datetime.now(timezone.utc)

            await _send_notifications(total_savings, len(resources), len(recommendations))

        except Exception as e:
            report.status = "error"
            report.resources = json.dumps({"error": str(e)})
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            logger.error("cost_analysis_failed", error=str(e), report_uuid=report_uuid)

    await db.commit()
    await db.refresh(report)
    return report


async def _send_notifications(savings: float, resources: int, recommendations: int):
    import httpx

    subject = f"AI Cost Analysis Report — ${savings:.2f}/month potential savings"
    message = (
        f"Cost Analysis Complete\n"
        f"Resources found: {resources}\n"
        f"Issues identified: {recommendations}\n"
        f"Potential monthly savings: ${savings:.2f}\n"
        f"View full report: {settings.site_url}/admin/cost-reports"
    )

    if settings.slack_webhook_url:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(settings.slack_webhook_url, json={
                    "text": f"*{subject}*\n\n{message}",
                })
        except Exception as e:
            logger.warning("slack_notification_failed", error=str(e))

    if settings.ses_from_email:
        try:
            import boto3
            ses = boto3.Session(region_name=settings.aws_region).client("ses")
            ses.send_email(
                Source=settings.ses_from_email,
                Destination={"ToAddresses": [settings.ses_from_email]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {"Text": {"Data": message}},
                },
            )
        except Exception as e:
            logger.warning("ses_notification_failed", error=str(e))


@router.post("/analysis/run", response_model=AnalysisRunResponse)
async def trigger_analysis(
    background_tasks: BackgroundTasks,
    body: AnalysisTriggerRequest,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    triggered_by = body.triggered_by

    async def run():
        try:
            async with __import__("app.db.session", fromlist=["async_session"]).async_session() as session:
                await _run_cost_analysis(session, triggered_by=triggered_by)
        except Exception as e:
            logger.error("background_task_failed", error=str(e))

    background_tasks.add_task(run)
    return AnalysisRunResponse(report_uuid="", status="started",
                                message="Analysis started in background")


@router.get("/analysis/reports/{report_id}", response_model=CostReportDetailResponse)
async def get_report(
    report_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CostReport).where(CostReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    import json

    def _as_list(raw: str | list | None) -> list:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []

    return CostReportDetailResponse(
        id=report.id,
        report_uuid=report.report_uuid,
        total_resources=report.total_resources or 0,
        total_recommendations=report.total_recommendations or 0,
        total_estimated_savings=report.total_estimated_savings or 0.0,
        status=report.status or "",
        triggered_by=report.triggered_by or "",
        created_at=report.created_at.isoformat() if report.created_at else "",
        completed_at=report.completed_at.isoformat() if report.completed_at else None,
        aws_account_id=report.aws_account_id or "",
        aws_region=report.aws_region or "",
        resources=_as_list(report.resources),
        recommendations=_as_list(report.recommendations),
    )


@router.get("/analysis/reports", response_model=list[CostReportResponse])
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CostReport).order_by(CostReport.created_at.desc()).limit(20)
    )
    reports = result.scalars().all()
    return [
        CostReportResponse(
            id=r.id, report_uuid=r.report_uuid,
            total_resources=r.total_resources,
            total_recommendations=r.total_recommendations,
            total_estimated_savings=r.total_estimated_savings,
            status=r.status, triggered_by=r.triggered_by,
            created_at=r.created_at.isoformat() if r.created_at else "",
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
        )
        for r in reports
    ]
