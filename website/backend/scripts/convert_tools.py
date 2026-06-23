#!/usr/bin/env python3
"""Convert tools.ts to tools.json for backend seeding."""
import json
import re
import os

TS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "src", "data", "tools.ts")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "app", "data", "tools.json")


def parse_tools_ts(filepath):
    with open(filepath) as f:
        content = f.read()

    cat_decl = "const categories: Category[] = ["
    cat_pos = content.index(cat_decl) + len(cat_decl)
    arr_start = cat_pos
    arr_end = content.rindex("]")
    array_text = content[arr_start:arr_end]

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
                cat_obj_text = array_text[start + 1: i]
                cat = _parse_category(cat_obj_text)
                if cat:
                    categories.append(cat)
        i += 1

    return categories


def _parse_category(text):
    def get_field(name):
        m = re.search(rf'{name}:\s*"((?:[^"\\]|\\.)*)"', text)
        return m.group(1) if m else None

    cat_id = get_field("id")
    if not cat_id:
        return None

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
    tools_text = text[bracket + 1: j - 1]

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
                tool_obj = tools_text[tool_start + 1: idx]
                tool = _parse_tool(tool_obj)
                if tool:
                    tools.append(tool)

    return {
        "slug": cat_id,
        "title": get_field("title") or cat_id,
        "description": get_field("description") or "",
        "icon": get_field("icon") or "🤖",
        "tools": tools,
    }


def _parse_tool(text):
    def get_field(name):
        m = re.search(rf'{name}:\s*"((?:[^"\\]|\\.)*)"', text)
        return m.group(1) if m else None

    def get_str_array(name):
        m = re.search(rf'{name}:\s*\[(.*?)\]', text, re.DOTALL)
        if not m:
            return []
        return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))

    def get_models():
        m = re.search(r'models:\s*\[(.*?)\]', text, re.DOTALL)
        if m:
            items = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
            return items if items else None
        m = re.search(r'models:\s*(undefined|null)', text)
        return None

    name = get_field("name")
    if not name:
        return None

    models = get_models()
    pros = get_str_array("pros")
    cons = get_str_array("cons")

    return {
        "name": name,
        "description": get_field("description") or "",
        "url": get_field("url") or "",
        "free_tier": get_field("freeTier"),
        "paid_tier": get_field("paidTier"),
        "best_for": get_field("bestFor"),
        "verdict": get_field("verdict"),
        "models": ", ".join(models) if models else None,
        "pros": "\n".join(f"- {p}" for p in pros) if pros else None,
        "cons": "\n".join(f"- {c}" for c in cons) if cons else None,
    }


def main():
    print(f"Reading {TS_FILE}...")
    categories = parse_tools_ts(TS_FILE)
    total_tools = sum(len(c["tools"]) for c in categories)
    print(f"Found {len(categories)} categories with {total_tools} tools")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(categories, f, indent=2, ensure_ascii=False)

    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
