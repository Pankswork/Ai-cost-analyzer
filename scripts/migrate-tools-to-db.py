#!/usr/bin/env python3
"""
Migration script: imports tools.ts data into PostgreSQL.

Run once after deploying the backend to populate the database.
Usage: DATABASE_URL=postgresql+asyncpg://user:pass@host/db python migrate-tools-to-db.py
"""

import os
import re
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text


TS_FILE = os.path.expanduser("~/projects/bestfreeaifor/src/data/tools.ts")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/bestfreeaifor")


def parse_tools_ts(filepath):
    """Parse tools.ts and extract categories with their tools."""
    with open(filepath) as f:
        content = f.read()

    categories = []
    cat_pattern = re.compile(
        r'{\s*id:\s*"([^"]+)"\s*,\s*title:\s*"([^"]+)"\s*,\s*description:\s*"([^"]*)"\s*,\s*icon:\s*"([^"]*)"\s*,\s*tools:\s*\[(.*?)\]\s*\}',
        re.DOTALL,
    )

    tool_pattern = re.compile(
        r'{\s*name:\s*"([^"]*)"\s*,\s*description:\s*"([^"]*)"\s*,\s*url:\s*"([^"]*)"\s*,\s*freeTier:\s*"([^"]*)"\s*,\s*paidTier:\s*([^,]*),\s*pros:\s*\[(.*?)\]\s*,\s*cons:\s*\[(.*?)\]\s*,\s*bestFor:\s*"([^"]*)"\s*,\s*verdict:\s*"([^"]*)"\s*(?:,\s*models:\s*\[(.*?)\])?\s*\}',
        re.DOTALL,
    )

    for cat_match in cat_pattern.finditer(content):
        cat_id = cat_match.group(1)
        title = cat_match.group(2)
        description = cat_match.group(3)
        icon = cat_match.group(4)
        tools_text = cat_match.group(5)

        tools = []
        for tool_match in tool_pattern.finditer(tools_text):
            models = tool_match.group(10)
            tools.append({
                "name": tool_match.group(1),
                "description": tool_match.group(2),
                "url": tool_match.group(3),
                "free_tier": tool_match.group(4),
                "paid_tier": tool_match.group(5) if tool_match.group(5) != "null" else None,
                "pros": [p.strip().strip('"') for p in tool_match.group(6).split(",") if p.strip()],
                "cons": [c.strip().strip('"') for c in tool_match.group(7).split(",") if c.strip()],
                "best_for": tool_match.group(8),
                "verdict": tool_match.group(9),
                "models": models.strip('"').split('","') if models else None,
            })

        categories.append({
            "id": cat_id,
            "title": title,
            "description": description,
            "icon": icon,
            "tools": tools,
        })

    return categories


async def migrate():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                slug VARCHAR(100) UNIQUE NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                icon VARCHAR(10) DEFAULT '🤖',
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tools (
                id SERIAL PRIMARY KEY,
                category_id INTEGER REFERENCES categories(id),
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(255) UNIQUE NOT NULL,
                description TEXT NOT NULL,
                url VARCHAR(500) NOT NULL,
                free_tier TEXT,
                paid_tier TEXT,
                best_for VARCHAR(255),
                verdict TEXT,
                models TEXT,
                pros TEXT,
                cons TEXT,
                sort_order INTEGER DEFAULT 0,
                is_published BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )
        """))

        print("Parsing tools.ts...")
        categories = parse_tools_ts(TS_FILE)
        print(f"Found {len(categories)} categories with {sum(len(c['tools']) for c in categories)} tools")

        for cat_idx, cat in enumerate(categories):
            slug = cat["id"]
            result = await conn.execute(
                text("SELECT id FROM categories WHERE slug = :slug"), {"slug": slug}
            )
            existing = result.fetchone()

            if existing:
                await conn.execute(
                    text("UPDATE categories SET title=:title, description=:description, icon=:icon, sort_order=:sort WHERE slug=:slug"),
                    {"slug": slug, "title": cat["title"], "description": cat["description"], "icon": cat["icon"], "sort": cat_idx},
                )
                cat_id = existing[0]
            else:
                result = await conn.execute(
                    text("INSERT INTO categories (slug, title, description, icon, sort_order) VALUES (:slug, :title, :description, :icon, :sort) RETURNING id"),
                    {"slug": slug, "title": cat["title"], "description": cat["description"], "icon": cat["icon"], "sort": cat_idx},
                )
                cat_id = result.fetchone()[0]

            for tool_idx, tool in enumerate(cat["tools"]):
                slug = re.sub(r'[^a-z0-9-]', '', f"{cat['id']}-{tool['name'].lower().replace(' ', '-')}")

                pros_str = "\n".join(f"- {p}" for p in tool["pros"]) if tool["pros"] else None
                cons_str = "\n".join(f"- {c}" for c in tool["cons"]) if tool["cons"] else None
                models_str = ", ".join(tool["models"]) if tool["models"] else None
                paid = tool["paid_tier"] if tool["paid_tier"] != "null" else None

                existing_tool = await conn.execute(
                    text("SELECT id FROM tools WHERE slug = :slug"), {"slug": slug}
                )
                if existing_tool.fetchone():
                    continue

                await conn.execute(
                    text("""INSERT INTO tools
                        (category_id, name, slug, description, url, free_tier, paid_tier, best_for, verdict, models, pros, cons, sort_order)
                        VALUES (:cat_id, :name, :slug, :desc, :url, :free, :paid, :best, :verdict, :models, :pros, :cons, :sort)"""),
                    {
                        "cat_id": cat_id, "name": tool["name"], "slug": slug,
                        "desc": tool["description"], "url": tool["url"],
                        "free": tool["free_tier"], "paid": paid,
                        "best": tool["best_for"], "verdict": tool["verdict"],
                        "models": models_str, "pros": pros_str, "cons": cons_str,
                        "sort": tool_idx,
                    },
                )

        print("Migration complete!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
