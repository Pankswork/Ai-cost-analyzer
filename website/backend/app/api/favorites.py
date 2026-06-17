from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.db.session import get_db
from app.models.tool import Tool, Favorite
from app.models.user import User
from app.models.pydantic_models import FavoriteResponse
from app.middleware.auth_middleware import get_current_user

router = APIRouter(tags=["favorites"])


@router.post("/favorites", status_code=status.HTTP_201_CREATED)
async def add_favorite(
    tool_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    existing = await db.execute(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.tool_id == tool_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already favorited")
    fav = Favorite(user_id=user.id, tool_id=tool_id)
    db.add(fav)
    await db.commit()
    return {"status": "favorited"}


@router.delete("/favorites/{tool_id}")
async def remove_favorite(
    tool_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(Favorite).where(Favorite.user_id == user.id, Favorite.tool_id == tool_id)
    )
    await db.commit()
    return {"status": "removed"}


@router.get("/favorites/check/{slug}")
async def check_favorite(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tool).where(Tool.slug == slug))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    existing = await db.execute(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.tool_id == tool.id)
    )
    return {"favorited": existing.scalar_one_or_none() is not None}


@router.post("/favorites/slug/{slug}", status_code=status.HTTP_201_CREATED)
async def add_favorite_by_slug(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tool).where(Tool.slug == slug))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    existing = await db.execute(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.tool_id == tool.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already favorited")
    fav = Favorite(user_id=user.id, tool_id=tool.id)
    db.add(fav)
    await db.commit()
    return {"status": "favorited"}


@router.delete("/favorites/slug/{slug}")
async def remove_favorite_by_slug(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tool).where(Tool.slug == slug))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    await db.execute(
        delete(Favorite).where(Favorite.user_id == user.id, Favorite.tool_id == tool.id)
    )
    await db.commit()
    return {"status": "removed"}


@router.get("/favorites", response_model=list[FavoriteResponse])
async def list_favorites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite, Tool.name, Tool.slug)
        .join(Tool, Favorite.tool_id == Tool.id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    )
    return [
        FavoriteResponse(
            tool_id=fav.tool_id,
            tool_name=name,
            tool_slug=slug,
            created_at=fav.created_at.isoformat() if fav.created_at else "",
        )
        for fav, name, slug in result.all()
    ]
