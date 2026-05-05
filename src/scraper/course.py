import asyncio
from playwright.async_api import async_playwright

from src.config.settings import ILIAS_DASHBOARD_URL
from src.scraper.auth import create_authenticated_context, verify_session
from src.scraper.parser import parse_courses, parse_items, find_course
from src.scraper.navigator import navigate_and_get_html, download_pdf
from src.rag.agent import select_relevant_items, get_current_semester_week
from src.rag.llm import complete


async def scrape_course(course_input: str) -> dict:
    """
    Main entry point. Given a course identifier (e.g. "I.BA_ITEO.F2601"),
    navigate ILIAS, find current materials, download PDFs, and summarize.
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
            print("Available courses:")
            for c in courses:
                print(f"  - {c.name}")
            await context.browser.close()
            return {"error": "course_not_found", "available": [c.name for c in courses]}

        print(f"🔍 Navigating: {target.name}")
        collected_texts = await _navigate_recursive(page, target.url, course_code, depth=0)

        await context.browser.close()

    if not collected_texts:
        print("\n⚠️  No materials found.")
        return {"course": course_input, "summary": None, "files": []}

    summary = _generate_summary(course_code, collected_texts)

    print(f"\n{'=' * 60}")
    print(f"📚 {course_input} — SW{get_current_semester_week()}")
    print(f"{'=' * 60}")
    print(summary)
    print(f"{'=' * 60}")

    return {
        "course": course_input,
        "summary": summary,
        "files": [t["name"] for t in collected_texts],
    }


async def _navigate_recursive(
    page, url: str, course_code: str, depth: int, max_depth: int = 3
) -> list[dict]:
    """Recursively navigate folders, guided by the RAG agent."""
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
        elif item.item_type == "file":
            text = await download_pdf(page, item, course_code)
            if text:
                collected.append({"name": item.name, "text": text})

    return collected


def _generate_summary(course_code: str, texts: list[dict]) -> str:
    """Use the LLM to create a concise lecture summary from extracted PDF texts."""
    sw = get_current_semester_week()

    combined = ""
    for t in texts:
        chunk = t["text"][:3000]
        combined += f"\n--- {t['name']} ---\n{chunk}\n"

    prompt = f"""You are my study assistant. Based on the following lecture materials for course {course_code} (semester week {sw}), give me a concise summary of what today's lecture covers.

Materials:
{combined}

Rules:
- Write in German, informal (du-Form)
- 5-8 sentences max
- Name the main topics, concepts, formulas, or methods covered
- Be specific — I want to know exactly what's being taught
- No fluff, no disclaimers"""

    return complete(prompt, max_tokens=600, temperature=0.1)


def _extract_code(course_input: str) -> str:
    """Extract short course code from full identifier. E.g. 'I.BA_ITEO.F2601' -> 'ITEO'"""
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

    course_input = sys.argv[1]
    asyncio.run(scrape_course(course_input))


if __name__ == "__main__":
    main()