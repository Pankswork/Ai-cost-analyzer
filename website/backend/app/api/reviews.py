from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.tool import Tool, Review
from app.models.user import User
from app.models.pydantic_models import ReviewCreate, ReviewResponse
from app.middleware.auth_middleware import get_current_user

router = APIRouter(tags=["reviews"])


@router.post("/tools/{slug}/reviews", status_code=status.HTTP_201_CREATED)
async def create_review(
    slug: str, body: ReviewCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tool).where(Tool.slug == slug, Tool.is_published == True))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    review = Review(user_id=user.id, tool_id=tool.id, rating=body.rating, body=body.body)
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return {"id": review.id, "status": "created"}


@router.get("/tools/{slug}/reviews", response_model=list[ReviewResponse])
async def list_reviews(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tool).where(Tool.slug == slug))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    reviews_result = await db.execute(
        select(Review, User.email)
        .join(User, Review.user_id == User.id)
        .where(Review.tool_id == tool.id)
        .order_by(Review.created_at.desc())
    )
    return [
        ReviewResponse(
            id=r.id, user_id=r.user_id, tool_id=r.tool_id,
            rating=r.rating, body=r.body,
            user_email=email,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r, email in reviews_result.all()
    ]
