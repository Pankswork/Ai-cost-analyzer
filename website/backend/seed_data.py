#!/usr/bin/env python3
"""Seed the database with tools data from tools.ts using backend models."""
import sys
import os
import re
import asyncio

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("APP_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/bestfreeaifor")  # local dev only

from app.db.session import async_session, engine, Base
from app.models.tool import Category, Tool
from sqlalchemy import text

TS_FILE = os.path.join(os.path.dirname(__file__), "..", "src", "data", "tools.ts")


def parse_tools_ts(filepath):
    with open(filepath) as f:
        content = f.read()

    # Find the categories array
    cat_decl = "const categories: Category[] = ["
    cat_pos = content.index(cat_decl) + len(cat_decl)
    arr_start = cat_pos
    # Must strip the leading newline/whitespace before the first {
    arr_end = content.rindex("]")
    array_text = content[arr_start : arr_end]

    categories = []
    depth = 0
    i = 0
    while i < len(array_text):
        c = array_text[i]
        if c == "{":
            depth += 1
            if depth == 1:
                start = i
        elif c == "}":
            depth -= 1
            if depth == 0:
                cat_obj_text = array_text[start + 1 : i]
                cat = _parse_category(cat_obj_text)
                if cat:
                    categories.append(cat)
        i += 1

    return categories


def _parse_category(text):
    cat = {}
    # Extract id
    m = re.search(r'id:\s*"([^"]+)"', text)
    if not m:
        return None
    cat["id"] = m.group(1)

    m = re.search(r'title:\s*"([^"]+)"', text)
    cat["title"] = m.group(1) if m else cat["id"]

    m = re.search(r'description:\s*"((?:[^"\\]|\\.)*)"', text)
    cat["description"] = m.group(1) if m else ""

    m = re.search(r'icon:\s*"([^"]*)"', text)
    cat["icon"] = m.group(1) if m else "🤖"

    # Find the tools array
    tools_start = text.index("tools:")
    bracket = text.index("[", tools_start)
    depth = 1
    j = bracket + 1
    while depth > 0 and j < len(text):
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
        j += 1
    tools_text = text[bracket + 1 : j - 1]

    tools = []
    depth = 0
    tool_start = -1
    for idx, ch in enumerate(tools_text):
        if ch == "{":
            if depth == 0:
                tool_start = idx
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and tool_start >= 0:
                tool_obj = tools_text[tool_start + 1 : idx]
                tool = _parse_tool(tool_obj)
                if tool:
                    tools.append(tool)
    cat["tools"] = tools
    return cat


def _parse_tool(text):
    def get_field(name):
        m = re.search(rf'{name}:\s*"((?:[^"\\]|\\.)*)"', text)
        return m.group(1) if m else None

    def get_str_array(name):
        m = re.search(rf'{name}:\s*\[(.*?)\]', text, re.DOTALL)
        if not m:
            return []
        items = []
        for item in re.finditer(r'"((?:[^"\\]|\\.)*)"', m.group(1)):
            items.append(item.group(1))
        return items

    def get_optional_str(name):
        m = re.search(rf'{name}:\s*"((?:[^"\\]|\\.)*)"', text)
        if m:
            return m.group(1)
        m = re.search(rf'{name}:\s*null', text)
        return None if m else None

    # Handle models which might be undefined, null, or array
    def get_models():
        m = re.search(r'models:\s*\[(.*?)\]', text, re.DOTALL)
        if m:
            items = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
            return items if items else None
        m = re.search(r'models:\s*(undefined|null)', text)
        return None

    tool = {
        "name": get_field("name"),
        "description": get_field("description"),
        "url": get_field("url"),
        "free_tier": get_field("freeTier"),
        "paid_tier": get_field("paidTier") if get_field("paidTier") else None,
        "pros": get_str_array("pros"),
        "cons": get_str_array("cons"),
        "best_for": get_field("bestFor"),
        "verdict": get_field("verdict"),
        "models": get_models(),
    }
    return tool


async def migrate():
    print("Parsing tools.ts...")
    categories = parse_tools_ts(TS_FILE)
    print(f"Found {len(categories)} categories with {sum(len(c['tools']) for c in categories)} tools")

    if not categories:
        print("No data parsed. Check the parsing logic.")
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Check if data already exists
        existing = await session.execute(text("SELECT COUNT(*) FROM categories"))
        count = existing.scalar()
        if count and count > 0:
            print(f"Database already has {count} categories. Skipping insert.")
            return

        for cat_idx, cat in enumerate(categories):
            slug = cat["id"]
            db_cat = Category(
                slug=slug,
                title=cat["title"],
                description=cat["description"],
                icon=cat.get("icon", "🤖"),
                sort_order=cat_idx,
            )
            session.add(db_cat)
            await session.flush()

            for tool_idx, tool in enumerate(cat["tools"]):
                name = tool.get("name") or ""
                raw_slug = f"{slug}-{name.lower().replace(' ', '-').replace('/', '-')}"
                clean_slug = re.sub(r"[^a-z0-9-]", "", raw_slug)
                clean_slug = re.sub(r"-+", "-", clean_slug)

                models_str = ", ".join(tool["models"]) if tool.get("models") else None
                pros_str = "\n".join(f"- {p}" for p in tool.get("pros", []))
                cons_str = "\n".join(f"- {c}" for c in tool.get("cons", []))

                db_tool = Tool(
                    category_id=db_cat.id,
                    name=name,
                    slug=clean_slug,
                    description=tool.get("description") or "",
                    url=tool.get("url") or "",
                    free_tier=tool.get("free_tier"),
                    paid_tier=tool.get("paid_tier"),
                    best_for=tool.get("best_for"),
                    verdict=tool.get("verdict"),
                    models=models_str,
                    pros=pros_str or None,
                    cons=cons_str or None,
                    sort_order=tool_idx,
                )
                session.add(db_tool)

        await session.commit()
        print(f"Successfully imported {len(categories)} categories and {sum(len(c['tools']) for c in categories)} tools!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
