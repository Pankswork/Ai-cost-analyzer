from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.models.user import User
from app.models.tool import Category, Tool, ToolSubmission
from app.models.misc import ContactMessage, NewsletterSubscriber, CostReport
import re
from app.middleware.auth_middleware import get_admin_user

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def admin_stats(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    tool_count = (await db.execute(select(func.count(Tool.id)))).scalar()
    cat_count = (await db.execute(select(func.count(Category.id)))).scalar()
    pending_subs = (await db.execute(
        select(func.count(ToolSubmission.id)).where(ToolSubmission.status == "pending")
    )).scalar()
    unread_msgs = (await db.execute(
        select(func.count(ContactMessage.id)).where(ContactMessage.replied is False)
    )).scalar()
    user_count = (await db.execute(select(func.count(User.id)))).scalar()
    sub_count = (await db.execute(
        select(func.count(NewsletterSubscriber.id)).where(NewsletterSubscriber.subscribed is True)
    )).scalar()
    return {
        "tools": tool_count, "categories": cat_count,
        "pending_submissions": pending_subs, "unread_messages": unread_msgs,
        "users": user_count, "subscribers": sub_count,
    }


@router.get("/submissions")
async def list_submissions(
    status_filter: str | None = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ToolSubmission).order_by(ToolSubmission.created_at.desc())
    if status_filter:
        query = query.where(ToolSubmission.status == status_filter)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/submissions/{submission_id}/approve")
async def approve_submission(
    submission_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ToolSubmission).where(ToolSubmission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    cat_result = await db.execute(select(Category).where(Category.slug == sub.category_slug))
    cat = cat_result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category")

    slug = re.sub(r'[^a-z0-9-]', '', sub.name.lower().replace(" ", "-"))
    tool = Tool(
        category_id=cat.id, name=sub.name, slug=slug,
        description=sub.description or "", url=sub.url,
    )
    db.add(tool)
    sub.status = "approved"
    sub.reviewed_by = admin.id
    from datetime import datetime, timezone
    sub.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "approved", "tool_id": tool.id}


@router.post("/submissions/{submission_id}/reject")
async def reject_submission(
    submission_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ToolSubmission).where(ToolSubmission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    sub.status = "rejected"
    sub.reviewed_by = admin.id
    from datetime import datetime, timezone
    sub.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "rejected"}


@router.get("/messages")
async def list_messages(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(100)
    )
    return result.scalars().all()


@router.get("/cost-reports")
async def list_cost_reports(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CostReport).order_by(CostReport.created_at.desc()).limit(50)
    )
    return result.scalars().all()


@router.get("/cost-reports/{report_id}")
async def get_cost_report(
    report_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CostReport).where(CostReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report
