from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.misc import ContactMessage, NewsletterSubscriber, AffiliateClick
from app.models.pydantic_models import ContactCreate, NewsletterSubscribe

router = APIRouter(tags=["misc"])


@router.post("/contact", status_code=status.HTTP_201_CREATED)
async def contact_submit(body: ContactCreate, db: AsyncSession = Depends(get_db)):
    msg = ContactMessage(name=body.name, email=str(body.email), message=body.message)
    db.add(msg)
    await db.commit()
    return {"status": "sent", "message": "We'll get back to you soon!"}


@router.post("/newsletter", status_code=status.HTTP_201_CREATED)
async def newsletter_subscribe(body: NewsletterSubscribe, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(NewsletterSubscriber)
        .where(NewsletterSubscriber.email == str(body.email))
    )
    if existing.scalar_one_or_none():
        return {"status": "already_subscribed"}
    sub = NewsletterSubscriber(email=str(body.email))
    db.add(sub)
    await db.commit()
    return {"status": "subscribed"}


@router.post("/affiliate/click")
async def track_affiliate_click(
    tool_id: int | None = None,
    url: str = "",
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    click = AffiliateClick(
        tool_id=tool_id,
        url=url,
        referrer=request.headers.get("referer", "") if request else "",
        user_agent=request.headers.get("user-agent", "") if request else "",
    )
    db.add(click)
    await db.commit()
    return {"status": "tracked"}
