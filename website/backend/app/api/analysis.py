import uuid
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.misc import CostReport
from app.models.user import User
from app.models.pydantic_models import AnalysisTriggerRequest, AnalysisRunResponse, CostReportResponse, CostReportDetailResponse
from app.config import settings
from app.middleware.auth_middleware import get_admin_user, get_current_user

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

    try:
        from app.services.aws_scanner import AwsResourceScanner
        from app.services.ai_analyzer import AiAnalyzer

        scanner = AwsResourceScanner()
        analyzer = AiAnalyzer()

        resources = await scanner.scan_resources()
        recommendations = await analyzer.analyze(resources)

        total_savings = sum(r.get("estimated_monthly_savings", 0) for r in recommendations)

        report.status = "completed"
        report.total_resources = len(resources)
        report.total_recommendations = len(recommendations)
        report.total_estimated_savings = total_savings
        report.resources = json.dumps([{
            "type": r.get("type"), "resource_id": r.get("resource_id"),
            "name": r.get("name"), "state": r.get("state"),
            "instance_type": r.get("instance_type"),
        } for r in resources])
        report.recommendations = json.dumps(recommendations)
        report.completed_at = datetime.now(timezone.utc)

        await _send_notifications(total_savings, len(resources), len(recommendations))

    except Exception as e:
        report.status = "error"
        report.resources = json.dumps({"error": str(e)})

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
        except Exception:
            pass

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
        except Exception:
            pass


@router.post("/analysis/run", response_model=AnalysisRunResponse)
async def trigger_analysis(
    background_tasks: BackgroundTasks,
    body: AnalysisTriggerRequest,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    triggered_by = body.triggered_by
    report_uuid = str(uuid.uuid4())
    report = CostReport(report_uuid=report_uuid, status="pending", triggered_by=triggered_by)
    db.add(report)
    await db.commit()

    async def run():
        async with __import__("app.db.session", fromlist=["async_session"]).async_session() as session:
            await _run_cost_analysis(session, triggered_by=triggered_by)

    background_tasks.add_task(run)
    return AnalysisRunResponse(report_uuid=report_uuid, status="started",
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
    resources_raw = report.resources
    recommendations_raw = report.recommendations

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
        resources=json.loads(resources_raw) if resources_raw and isinstance(resources_raw, str) else (resources_raw if isinstance(resources_raw, list) else []),
        recommendations=json.loads(recommendations_raw) if recommendations_raw and isinstance(recommendations_raw, str) else (recommendations_raw if isinstance(recommendations_raw, list) else []),
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
