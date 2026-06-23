import json
import os
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.models.tool import Category, Tool

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "tools.json")


async def seed_database(db: AsyncSession) -> None:
    existing = await db.execute(text("SELECT COUNT(*) FROM categories"))
    count = existing.scalar()
    if count and count > 0:
        return

    if not os.path.isfile(DATA_FILE):
        print(f"Seed data file not found: {DATA_FILE}")
        return

    with open(DATA_FILE) as f:
        categories_data = json.load(f)

    for cat_idx, cat in enumerate(categories_data):
        db_cat = Category(
            slug=cat["slug"],
            title=cat["title"],
            description=cat["description"],
            icon=cat.get("icon", "🤖"),
            sort_order=cat_idx,
        )
        db.add(db_cat)
        await db.flush()

        for tool_idx, tool in enumerate(cat["tools"]):
            slug_raw = f"{cat['slug']}-{tool['name'].lower().replace(' ', '-').replace('/', '-')}"
            clean_slug = re.sub(r"[^a-z0-9-]", "", slug_raw)
            clean_slug = re.sub(r"-+", "-", clean_slug)

            db_tool = Tool(
                category_id=db_cat.id,
                name=tool["name"],
                slug=clean_slug,
                description=tool.get("description") or "",
                url=tool.get("url") or "",
                free_tier=tool.get("free_tier"),
                paid_tier=tool.get("paid_tier"),
                best_for=tool.get("best_for"),
                verdict=tool.get("verdict"),
                models=tool.get("models"),
                pros=tool.get("pros"),
                cons=tool.get("cons"),
                sort_order=tool_idx,
                is_published=True,
            )
            db.add(db_tool)

    await db.commit()
    print(f"Seeded {len(categories_data)} categories and {sum(len(c['tools']) for c in categories_data)} tools")
