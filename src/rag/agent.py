import re
from datetime import date

from src.scraper.parser import IliasItem
from src.rag.llm import complete
from src.rag.indexer import query as rag_query


def get_current_semester_week() -> int:
    kw = date.today().isocalendar()[1]
    if 8 <= kw <= 30:
        return kw - 7   # Spring semester
    elif kw >= 38:
        return kw - 37  # Fall semester
    return 1


def select_relevant_items(
    items: list[IliasItem],
    course_code: str,
    depth: int,
) -> list[int]:
    """
    Use RAG context + LLM to decide which ILIAS items are relevant
    for the current week's lecture materials.
    """
    sw = get_current_semester_week()

    rag_context = _get_rag_context(course_code, sw)

    items_text = "\n".join(
        f"  [{i}] {'📁' if item.item_type == 'folder' else '📄'} {item.name}"
        for i, item in enumerate(items)
    )

    prompt = f"""You are helping me find the current lecture materials on the ILIAS learning platform.

Course: {course_code}
Current semester week: SW{sw}
Navigation depth: {depth} (0 = course root, 1 = subfolder, etc.)
{rag_context}

Items on the current page:
{items_text}

Task: Which items contain the lecture materials for SW{sw}?

Rules:
- Depth 0: Pick the folder with lecture materials (e.g. "Unterlagen", "Material", "Vorlesungen", "Inhalt")
- Depth 1+: Pick the folder matching SW{sw}. This can be:
  * "SW {sw}" or "SW{sw}" in the name
  * Numbered folders like "{sw:02d} ..." where the number = semester week
  * If no exact match, pick the highest numbered folder (= latest content)
- Also select PDF files that look like current lecture slides
- Ignore: Forum, Abgabe, Kommunikation, Leistungsnachweis, Info, Probeprüfung
- Reply ONLY with comma-separated item numbers. Example: 2,5
- If nothing fits: NONE"""

    try:
        answer = complete(prompt, max_tokens=50)
        print(f"    🤖 LLM: {answer}")

        if "NONE" in answer.upper():
            return []

        indices = []
        for num in re.findall(r"\d+", answer):
            idx = int(num)
            if 0 <= idx < len(items):
                indices.append(idx)
        return indices

    except Exception as e:
        print(f"    ⚠️  LLM error: {e}")
        return _fallback(items, sw, depth)


def _get_rag_context(course_code: str, sw: int) -> str:
    """Query the RAG for module description context about the current week."""
    try:
        chunks = rag_query(f"{course_code} Semesterwoche {sw} SW{sw} Thema Inhalt")
        if chunks:
            context = "\n".join(chunks[:3])
            return f"\nModule description context for this week:\n{context}\n"
    except Exception:
        pass
    return ""


def _fallback(items: list[IliasItem], sw: int, depth: int) -> list[int]:
    """Rule-based fallback when LLM is unavailable."""
    if depth == 0:
        keywords = ["unterlagen", "material", "vorlesung", "inhalt", "skript", "folien"]
        matches = [
            i for i, item in enumerate(items)
            if item.item_type == "folder" and any(k in item.name.lower() for k in keywords)
        ]
        if matches:
            return matches

    # Match SW pattern
    sw_patterns = [f"sw{sw}", f"sw {sw}"]
    if sw < 10:
        sw_patterns.append(f"sw0{sw}")
    matches = [
        i for i, item in enumerate(items)
        if any(p in item.name.lower() for p in sw_patterns)
    ]
    if matches:
        return matches

    # Match numbered folders
    numbered = []
    for i, item in enumerate(items):
        m = re.match(r"^0?(\d{1,2})\b", item.name.strip())
        if m:
            numbered.append((int(m.group(1)), i))
    if numbered:
        numbered.sort(reverse=True)
        return [numbered[0][1]]

    # Last resort: last two folders
    folders = [i for i, item in enumerate(items) if item.item_type == "folder"]
    return folders[-2:] if len(folders) >= 2 else folders