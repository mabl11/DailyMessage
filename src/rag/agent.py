import re
import os
from datetime import date

from src.scraper.parser import IliasItem
from src.rag.llm import complete
from src.rag.indexer import get_full_text

IGNORE_KEYWORDS = [
    "zusatz", "optional", "literatur", "aufzeichnung", "recording",
    "zoom", "forum", "abgabe", "kommunikation", "leistungsnachweis",
    "probeprüfung", "administration", "prüfungsvorbereitung",
    "lernkontrolle", "ip-insider", "beispiel", "template",
    "dokumentation", "links", "einführungsaufgabe",
]

FILE_IGNORE_KEYWORDS = [
    "lernkontrolle", "ip-insider", "beispiel", "template",
    "dokumentation", "links", "einführungsaufgabe", "ballooning",
    "dedup", "lifecycle", "perf_memory", "vsp_", "introducing",
    "never touch", "aufgabenbl",
]


def get_current_semester_week() -> int:
    kw = date.today().isocalendar()[1]
    offset = int(os.getenv("SW_OFFSET", "0"))
    if 8 <= kw <= 30:
        return (kw - 7) + offset
    elif kw >= 38:
        return (kw - 37) + offset
    return 1


def select_relevant_items(
    items: list[IliasItem],
    course_code: str,
    depth: int,
) -> list[int]:
    if depth == 0:
        return _select_root_folder(items)

    sw = get_current_semester_week()
    has_folders = any(i.item_type == "folder" for i in items)

    if has_folders:
        return _select_folder(items, course_code, sw)
    return _select_files(items, course_code, sw)


# -------------------------------------------------------------------------
# Depth 0
# -------------------------------------------------------------------------
def _select_root_folder(items: list[IliasItem]) -> list[int]:
    keywords = ["unterlagen", "material", "vorlesung", "inhalt", "skript",
                "folien", "slides", "serien", "kohorten"]
    matches = [
        i for i, item in enumerate(items)
        if item.item_type == "folder"
        and any(k in item.name.lower() for k in keywords)
        and not _is_ignored(item)
    ]
    if matches:
        print(f"    ✅ root: {items[matches[0]].name}")
        return matches

    items_text = "\n".join(f"  [{i}] {item.name}" for i, item in enumerate(items))
    answer = complete(
        f"Which folder contains lecture materials?\n{items_text}\nReply with number only.",
        max_tokens=10,
    )
    print(f"    🤖 root: {answer}")
    return _parse_indices(answer, len(items))


# -------------------------------------------------------------------------
# Folder selection
# -------------------------------------------------------------------------
def _select_folder(items: list[IliasItem], course_code: str, sw: int) -> list[int]:
    direct = _match_sw_in_name(items, sw)
    if direct:
        print(f"    ✅ SW name: {', '.join(items[i].name for i in direct)}")
        return direct

    desc = _match_sw_in_description(items, sw)
    if desc:
        print(f"    ✅ SW desc: {', '.join(items[i].name for i in desc)}")
        return desc

    topic = _try_topic_match_folders(items, course_code, sw)
    if topic:
        print(f"    ✅ topic: {', '.join(items[i].name for i in topic)}")
        return topic

    highest = _fallback_highest(items)
    if highest:
        print(f"    ✅ fallback: {items[highest[0]].name}")
    return highest


# -------------------------------------------------------------------------
# File selection
# -------------------------------------------------------------------------
def _select_files(items: list[IliasItem], course_code: str, sw: int) -> list[int]:
    relevant = [
        (i, item) for i, item in enumerate(items)
        if item.item_type == "file" and not _is_ignored_file(item)
    ]
    if not relevant:
        relevant = [(i, item) for i, item in enumerate(items) if item.item_type == "file"]

    # Strategy 1: SW/serie match in filename
    sw_files = [i for i, item in relevant if _name_matches_sw(item.name, sw)]
    if sw_files:
        print(f"    ✅ SW files: {', '.join(items[i].name for i in sw_files)}")
        return sw_files

    # Strategy 2: LLM with mapping context
    full_text = get_full_text(course_code) or ""
    mapping_context = ""
    for line in full_text.split("\n"):
        if f"SW{sw}" in line or f"SW {sw}" in line:
            mapping_context += line + "\n"

    items_text = "\n".join(f"  [{i}] {item.name}" for i, item in relevant)

    prompt = f"""Pick the main lecture slides/folien for {course_code} SW{sw}.

{f"Schedule says SW{sw}: {mapping_context}" if mapping_context else ""}

Files:
{items_text}

Rules:
- Pick the MAIN lecture slides (usually named after the topic or chapter)
- Ignore: Lernkontrolle, examples, templates, external articles, ip-insider, supplementary materials
- A file named the same as its parent folder is usually the main slide
- Pick 1-3 files max

Reply with ONLY numbers, comma-separated."""

    answer = complete(prompt, max_tokens=20)
    print(f"    🤖 files: {answer}")
    return _parse_indices(answer, len(items))


# -------------------------------------------------------------------------
# Matching
# -------------------------------------------------------------------------
def _match_sw_in_name(items: list[IliasItem], sw: int) -> list[int]:
    patterns = [
        f"sw {sw} ", f"sw {sw}-", f"sw{sw} ", f"sw{sw}-",
        f"sw {sw:02d} ", f"sw{sw:02d} ", f"sw{sw:02d}-",
    ]
    return [
        i for i, item in enumerate(items)
        if any(p in item.name.lower() + " " for p in patterns)
    ]


def _match_sw_in_description(items: list[IliasItem], sw: int) -> list[int]:
    matches = []
    for i, item in enumerate(items):
        combined = f"{item.name} {item.description}".lower()

        if re.search(rf'\bsw\s*0?{sw}\b', combined):
            matches.append(i)
            continue

        for start, end in re.findall(r'sw\s*(\d+)\s*[-–]\s*sw\s*(\d+)', combined):
            if int(start) <= sw <= int(end):
                matches.append(i)
                break

        for a, b in re.findall(r'sw\s*(\d+)\s*\+\s*sw\s*(\d+)', combined):
            if sw in (int(a), int(b)):
                matches.append(i)
                break

    return matches


def _name_matches_sw(name: str, sw: int) -> bool:
    lower = name.lower()
    patterns = [
        rf'sw[-_\s]?0?{sw}\b', rf'serie[-_\s]?0?{sw}\b',
        rf'[-_]sw0?{sw}[-_\s]',
    ]
    return any(re.search(p, lower) for p in patterns)


def _try_topic_match_folders(items: list[IliasItem], course_code: str, sw: int) -> list[int]:
    full_text = get_full_text(course_code)
    if not full_text:
        return []

    today_name = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                  "Freitag", "Samstag", "Sonntag"][date.today().weekday()]

    items_text = "\n".join(
        f"  [{i}] {'📁' if item.item_type == 'folder' else '📄'} {item.name}"
        + (f" ({item.description})" if item.description else "")
        for i, item in enumerate(items)
    )

    prompt = f"""Find today's lecture folders.

MAPPING/SCHEDULE:
{full_text[:6000]}

TODAY: {today_name}, SW{sw}

ITEMS:
{items_text}

Find the line for SW{sw} in the mapping. It lists EXACT folder names separated by "/".
Match ONLY those exact names to the items. Be PRECISE about sub-numbers:
- If mapping says "5.4 OS-Virtualisierung", pick ONLY "5.4", NOT "5.3" or "5.2"
- If mapping says "05 Virtualisierung im DC; 5.4", pick the parent folder "05" AND sub-folder "5.4" if visible

Reply with ONLY the matching item numbers. Example: 4,9
If nothing matches: NONE"""

    answer = complete(prompt, max_tokens=30)
    print(f"    🤖 topic: {answer}")
    return _parse_indices(answer, len(items))


def _fallback_highest(items: list[IliasItem]) -> list[int]:
    numbered = []
    for i, item in enumerate(items):
        if item.item_type != "folder":
            continue
        m = re.match(r"^(?:Kap\.?\s*)?0?(\d{1,2})\b", item.name.strip())
        if m:
            numbered.append((int(m.group(1)), i))
    if numbered:
        numbered.sort(reverse=True)
        return [numbered[0][1]]
    folders = [i for i, item in enumerate(items) if item.item_type == "folder"]
    return folders[-2:] if len(folders) >= 2 else folders


def _is_ignored(item: IliasItem) -> bool:
    lower = f"{item.name} {item.description}".lower()
    return any(k in lower for k in IGNORE_KEYWORDS)


def _is_ignored_file(item: IliasItem) -> bool:
    lower = item.name.lower()
    return any(k in lower for k in FILE_IGNORE_KEYWORDS)


def _parse_indices(text: str, max_len: int) -> list[int]:
    if "NONE" in text.upper():
        return []
    return [int(n) for n in re.findall(r"\d+", text) if 0 <= int(n) < max_len]