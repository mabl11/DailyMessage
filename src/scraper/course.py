import asyncio
from playwright.async_api import async_playwright

from src.config.settings import ILIAS_DASHBOARD_URL
from src.scraper.auth import create_authenticated_context, verify_session
from src.scraper.parser import parse_courses, parse_items, find_course
from src.scraper.navigator import navigate_and_get_html
from src.rag.agent import select_relevant_items, get_current_semester_week


async def scrape_course(course_input: str) -> dict:
    """
    Given a course identifier (e.g. "I.BA_ITEO.F2601"),
    navigate ILIAS, find current materials, return file names.
    """
    course_code = _extract_code(course_input)

    async with async_playwright() as p:
        context = await create_authenticated_context(p)
        page = await context.new_page()

        print(f"\n📡 Loading ILIAS dashboard...")
        html = await navigate_and_get_html(page, ILIAS_DASHBOARD_URL)

        if not await verify_session(page):
            print("❌ Session expired. Run: python -m src.scraper.auth")
            await context.browser.close()
            return {"error": "session_expired"}

        courses = parse_courses(html)
        print(f"📚 {len(courses)} courses found")

        target = find_course(courses, course_code)
        if not target:
            target = find_course(courses, course_input)
        if not target:
            print(f"❌ Course '{course_input}' not found.")
            for c in courses:
                print(f"  - {c.name}")
            await context.browser.close()
            return {"error": "course_not_found", "available": [c.name for c in courses]}

        print(f"🔍 Navigating: {target.name}")
        files = await _navigate_recursive(page, target.url, course_code, depth=0)

        await context.browser.close()

    if not files:
        print("\n⚠️  No materials found.")
        return {"course": course_input, "files": []}

    sw = get_current_semester_week()
    print(f"\n{'=' * 60}")
    print(f"📚 {course_input} — SW{sw}")
    print(f"{'=' * 60}")
    for f in files:
        print(f"  📄 {f}")
    print(f"{'=' * 60}")

    return {"course": course_input, "files": files}


async def _navigate_recursive(
    page, url: str, course_code: str, depth: int, max_depth: int = 3
) -> list[str]:
    """Recursively navigate folders, collect file names selected by the agent."""
    if depth > max_depth:
        return []

    html = await navigate_and_get_html(page, url)
    items = parse_items(html)

    if not items:
        return []

    indent = "  " * (depth + 1)
    print(f"{indent}📋 {len(items)} items (depth {depth})")
    for item in items:
        icon = "📁" if item.item_type == "folder" else "📄"
        print(f"{indent}  {icon} {item.name}")

    selected = select_relevant_items(items, course_code, depth)
    if not selected:
        print(f"{indent}  ⚠️  nothing relevant found")
        return []

    collected = []
    for idx in selected:
        item = items[idx]
        print(f"{indent}  → selected: {item.name}")

        if item.item_type == "folder":
            sub = await _navigate_recursive(page, item.url, course_code, depth + 1)
            collected.extend(sub)
        else:
            collected.append(item.name)

    return collected


def _extract_code(course_input: str) -> str:
    import re
    match = re.search(r"I\.BA_([A-Z]{2,10})(?:_[A-Z])?[\._]", course_input)
    if match:
        return match.group(1)
    return course_input


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.scraper.course <course_identifier>")
        print('Example: python -m src.scraper.course "I.BA_ITEO.F2601"')
        sys.exit(1)
    asyncio.run(scrape_course(sys.argv[1]))


if __name__ == "__main__":
    main()