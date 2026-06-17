from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.tool import ToolSubmission
from app.models.pydantic_models import ToolSubmissionCreate

router = APIRouter(tags=["submissions"])


@router.post("/submissions", status_code=status.HTTP_201_CREATED)
async def submit_tool(body: ToolSubmissionCreate, db: AsyncSession = Depends(get_db)):
    submission = ToolSubmission(
        name=body.name,
        url=body.url,
        category_slug=body.category_slug,
        description=body.description,
        submitter_email=body.submitter_email,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return {"id": submission.id, "status": "pending", "message": "Thank you! We'll review your submission."}
