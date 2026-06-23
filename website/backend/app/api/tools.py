from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.db.session import get_db
from app.models.tool import Category, Tool
from app.models.pydantic_models import ToolResponse, ToolListResponse, CategoryResponse

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    category: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Tool).where(Tool.is_published == True)
    count_query = select(func.count(Tool.id)).where(Tool.is_published == True)

    if category:
        cat_result = await db.execute(select(Category).where(Category.slug == category))
        cat = cat_result.scalar_one_or_none()
        if cat:
            query = query.where(Tool.category_id == cat.id)
            count_query = count_query.where(Tool.category_id == cat.id)

    if search:
        search_filter = or_(
            Tool.name.ilike(f"%{search}%"),
            Tool.description.ilike(f"%{search}%"),
            Tool.best_for.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Tool.sort_order).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tools = result.scalars().all()

    tool_responses = []
    for t in tools:
        cat = await db.get(Category, t.category_id)
        tool_responses.append(ToolResponse(
            id=t.id, name=t.name, slug=t.slug, description=t.description,
            url=t.url, free_tier=t.free_tier, paid_tier=t.paid_tier,
            best_for=t.best_for, verdict=t.verdict, models=t.models,
            pros=t.pros, cons=t.cons,
            category_slug=cat.slug if cat else None,
            category_title=cat.title if cat else None,
            category_icon=cat.icon if cat else None,
        ))

    return ToolListResponse(tools=tool_responses, total=total, page=page, page_size=page_size)


@router.get("/tools/{slug}", response_model=ToolResponse)
async def get_tool(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tool).where(Tool.slug == slug, Tool.is_published == True)
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    cat = await db.get(Category, tool.category_id)
    return ToolResponse(
        id=tool.id, name=tool.name, slug=tool.slug, description=tool.description,
        url=tool.url, free_tier=tool.free_tier, paid_tier=tool.paid_tier,
        best_for=tool.best_for, verdict=tool.verdict, models=tool.models,
        pros=tool.pros, cons=tool.cons,
        category_slug=cat.slug if cat else None,
        category_title=cat.title if cat else None,
        category_icon=cat.icon if cat else None,
    )


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Category, func.count(Tool.id).label("tool_count"))
        .outerjoin(Tool, Tool.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.sort_order)
    )
    rows = result.all()
    return [
        CategoryResponse(id=cat.id, slug=cat.slug, title=cat.title,
                         description=cat.description, icon=cat.icon,
                         tool_count=tool_count)
        for cat, tool_count in rows
    ]


@router.get("/search")
async def search_tools(q: str = Query(min_length=1), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tool).where(
            Tool.is_published == True,
            or_(
                func.to_tsvector("english", Tool.name).op("@@")(
                    func.plainto_tsquery("english", q)
                ),
                func.to_tsvector("english", Tool.description).op("@@")(
                    func.plainto_tsquery("english", q)
                ),
            )
        ).limit(20)
    )
    tools = result.scalars().all()
    return [{"id": t.id, "name": t.name, "slug": t.slug, "best_for": t.best_for} for t in tools]
