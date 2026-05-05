"""
HSLU ILIAS Scraper – Intelligenter Agent
==========================================
Nutzt Claude um die Kursstruktur zu verstehen und die richtigen
Materialien zu finden – egal wie der Dozent den Kurs organisiert hat.

Modi:
  python ilias_scraper.py login              → Manueller Login
  python ilias_scraper.py scrape             → Kursübersicht
  python ilias_scraper.py scrape "ANAF"      → Intelligentes Scraping

Voraussetzungen:
  pip install playwright beautifulsoup4 pymupdf anthropic python-dotenv
  playwright install chromium
"""

import asyncio
import json
import re
import os
import sys
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
COOKIES_FILE = Path("ilias_cookies.json")
ILIAS_DASHBOARD_URL = (
    "https://elearning.hslu.ch/ilias/ilias.php"
    "?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems"
)
ILIAS_BASE_URL = "https://elearning.hslu.ch"
PDF_CACHE_DIR = Path("pdf_cache")
PDF_CACHE_DIR.mkdir(exist_ok=True)

PAGE_TIMEOUT = 30_000
MAX_PDF_PAGES = 15
MAX_TEXT_PER_PDF = 5000


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
async def do_login():
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("ILIAS Login – Manueller Modus")
    print("=" * 60)
    print("\nBrowser wird geöffnet. Logge dich via SWITCHaai + 2FA ein.")
    print("Danach hier ENTER drücken.\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(ILIAS_DASHBOARD_URL, timeout=PAGE_TIMEOUT)
        input(">>> ENTER wenn eingeloggt... ")
        cookies = await context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))
        print(f"✅ {len(cookies)} Cookies gespeichert.")
        await browser.close()


# ---------------------------------------------------------------------------
# Intelligenter Agent: Llama (via Groq) entscheidet wohin navigiert wird
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


def ask_llm_which_folder(items: list[dict], course_code: str, depth: int) -> list[int]:
    """
    Zeigt dem LLM die Items auf einer ILIAS-Seite und fragt:
    'Welche Ordner/Dateien enthalten die aktuellen Vorlesungsmaterialien?'

    Nutzt Groq (Llama 3.3 70B) – kostenlos & ultraschnell.
    Gibt eine Liste von Indizes zurück.
    """
    from openai import OpenAI

    if not GROQ_API_KEY:
        return _fallback_selection(items, depth)

    sw = get_current_week_number()

    items_text = "\n".join(
        f"  [{i}] {'📁 Ordner' if item['type'] == 'folder' else '📄 Datei'}: {item['name']}"
        for i, item in enumerate(items)
    )

    prompt = f"""Du bist ein Assistent der mir hilft, auf der ILIAS-Lernplattform die aktuellen Vorlesungsmaterialien zu finden.

Kurs: {course_code}
Aktuelle Semesterwoche: SW{sw}
Navigationstiefe: {depth} (0 = Kurshauptseite, 1 = erster Unterordner, etc.)

Hier sind die Items auf der aktuellen Seite:
{items_text}

Aufgabe: Welche Items enthalten wahrscheinlich die aktuellen Vorlesungsunterlagen (Folien, Skripte, Übungen) für diese Woche?

Regeln:
- Bei Tiefe 0: Wähle den Ordner der Vorlesungsmaterialien enthält (z.B. "Unterlagen", "Materialien", "Inhalt", "Vorlesungen", etc.)
- Bei Tiefe 1+: Wähle den Ordner der aktuellen Semesterwoche (SW{sw}) oder den neuesten/letzten Ordner falls kein SW-Match
- Wähle auch direkte PDF-Dateien die nach SW{sw} benannt sind
- Ignoriere administrative Ordner (Forum, Abgabe, Kommunikation, Leistungsnachweis, Info)
- Antworte NUR mit den Nummern der relevanten Items, kommagetrennt. Beispiel: 2,5,7
- Falls nichts passt, antworte mit: NONE"""

    try:
        client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=50,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.choices[0].message.content.strip()
        print(f"     🤖 LLM sagt: {answer}")

        if "NONE" in answer.upper():
            return []

        indices = []
        for part in re.findall(r"\d+", answer):
            idx = int(part)
            if 0 <= idx < len(items):
                indices.append(idx)

        return indices

    except Exception as e:
        print(f"     ⚠️  Groq-Fehler: {e}")
        return _fallback_selection(items, depth)


def _fallback_selection(items: list[dict], depth: int) -> list[int]:
    """Regelbasierter Fallback falls kein API-Key oder Claude-Fehler."""
    sw = get_current_week_number()
    selected = []

    if depth == 0:
        # Oberste Ebene: Ordner mit Material-Keywords suchen
        keywords = ["unterlagen", "material", "vorlesung", "inhalt", "skript", "folien"]
        for i, item in enumerate(items):
            if item["type"] == "folder" and any(k in item["name"].lower() for k in keywords):
                selected.append(i)
    else:
        # Tiefere Ebene: SW-Ordner oder letzte Einträge
        sw_patterns = [f"sw{sw}", f"sw {sw}", f"sw0{sw}" if sw < 10 else ""]
        for i, item in enumerate(items):
            if any(p and p in item["name"].lower() for p in sw_patterns):
                selected.append(i)

    # Fallback: Letzte 2 Ordner (neueste)
    if not selected:
        folders = [i for i, item in enumerate(items) if item["type"] == "folder"]
        selected = folders[-2:] if len(folders) >= 2 else folders

    # Oder letzte 3 Dateien
    if not selected:
        files = [i for i, item in enumerate(items) if item["type"] == "file"]
        selected = files[-3:]

    return selected


# ---------------------------------------------------------------------------
# Rekursiver Scrape mit intelligentem Agent
# ---------------------------------------------------------------------------
async def scrape_course_deep(page, course_url: str, course_code: str, max_depth: int = 3) -> dict:
    """
    Navigiert intelligent durch einen ILIAS-Kurs:
    1. Seite laden, Items parsen
    2. Claude fragen: welche Items sind relevant?
    3. In relevante Ordner navigieren (rekursiv)
    4. PDFs herunterladen & Text extrahieren
    """
    collected_pdfs = []
    all_item_names = []

    async def _navigate(url: str, depth: int):
        if depth > max_depth:
            return

        from bs4 import BeautifulSoup

        await page.goto(url, timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(2000)
        soup = BeautifulSoup(await page.content(), "html.parser")
        items = parse_all_items(soup)

        if not items:
            return

        indent = "  " + "  " * depth
        print(f"{indent}📋 {len(items)} Items (Tiefe {depth})")
        for item in items:
            icon = "📁" if item["type"] == "folder" else "📄"
            print(f"{indent}   {icon} {item['name']}")
            all_item_names.append(item["name"])

        # Claude fragen welche Items relevant sind
        selected = ask_llm_which_folder(items, course_code, depth)

        if not selected:
            print(f"{indent}   ⚠️  Nichts Relevantes gefunden.")
            return

        for idx in selected:
            item = items[idx]
            print(f"{indent}   → Ausgewählt: {item['name']}")

            if item["type"] == "folder":
                # Rekursiv in Ordner navigieren
                await _navigate(item["url"], depth + 1)
            elif item["type"] == "file":
                # PDF herunterladen & Text extrahieren
                text = await _download_and_extract(page, item, course_code)
                collected_pdfs.append({"name": item["name"], "text": text})

    await _navigate(course_url, depth=0)

    return {
        "pdfs": [p for p in collected_pdfs if p["text"]],
        "all_items": all_item_names,
    }


# ---------------------------------------------------------------------------
# PDF Download & Text Extraction
# ---------------------------------------------------------------------------
async def _download_and_extract(page, item: dict, course_code: str) -> str | None:
    """Lädt PDF herunter und extrahiert Text."""
    import fitz

    filename = _safe_filename(f"{course_code}_{item['name']}")
    cache_path = PDF_CACHE_DIR / filename
    text_cache = cache_path.with_suffix(".txt")

    # Text-Cache
    if text_cache.exists():
        print(f"        📦 Cache: {item['name']}")
        return text_cache.read_text(encoding="utf-8")

    # PDF-Cache
    if cache_path.exists() and cache_path.stat().st_size > 0:
        text = _extract_pdf_text(cache_path)
        if text:
            text_cache.write_text(text, encoding="utf-8")
        return text

    # Download
    print(f"        📥 Lade: {item['name']}...")
    try:
        async with page.expect_download(timeout=15000) as dl_info:
            await page.goto(item["url"], timeout=PAGE_TIMEOUT)
        download = await dl_info.value
        await download.save_as(str(cache_path))
    except Exception:
        try:
            resp = await page.goto(item["url"], timeout=PAGE_TIMEOUT)
            if resp:
                ct = resp.headers.get("content-type", "")
                if "pdf" in ct or "octet" in ct:
                    cache_path.write_bytes(await resp.body())
                else:
                    print(f"        ⚠️  Kein PDF: {item['name']}")
                    return None
        except Exception as e:
            print(f"        ❌ Fehler: {e}")
            return None

    text = _extract_pdf_text(cache_path)
    if text:
        text_cache.write_text(text, encoding="utf-8")
        print(f"        ✅ {len(text)} Zeichen extrahiert")
    return text


def _extract_pdf_text(pdf_path: Path) -> str | None:
    import fitz
    try:
        doc = fitz.open(str(pdf_path))
        parts = []
        for i in range(min(len(doc), MAX_PDF_PAGES)):
            t = doc[i].get_text()
            if t.strip():
                parts.append(t.strip())
        doc.close()
        text = "\n\n".join(parts)
        if len(text) > MAX_TEXT_PER_PDF:
            text = text[:MAX_TEXT_PER_PDF] + "\n[... gekürzt]"
        return text if text.strip() else None
    except Exception as e:
        print(f"        ⚠️  PDF-Fehler: {e}")
        return None


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\s.-]", "", name)
    name = re.sub(r"\s+", "_", name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name[:100]


# ---------------------------------------------------------------------------
# HTML Parsing (HSLU ILIAS)
# ---------------------------------------------------------------------------
def parse_all_items(soup) -> list[dict]:
    """Extrahiert alle Items von einer ILIAS-Seite."""
    items = []

    for row in soup.select(".ilCLI, .ilObjListRow"):
        item = _parse_item(row)
        if item:
            items.append(item)

    # Fallback
    if not items:
        for block in soup.select(".ilContainerBlock"):
            for row in block.select(".ilCLI, .ilObjListRow"):
                item = _parse_item(row)
                if item:
                    items.append(item)

    seen = set()
    return [i for i in items if i["url"] not in seen and not seen.add(i["url"])]


def _parse_item(el) -> dict | None:
    link = el.select_one("h3.il_ContainerItemTitle a")
    if not link:
        link = el.select_one("a[href*='sendfile']")
    if not link:
        link = el.select_one("a[href*='ref_id']")
    if not link:
        link = el.select_one("a[href*='ilias.php']")
    if not link:
        return None

    name = link.get_text(strip=True)
    if not name or len(name) < 2:
        return None

    href = link.get("href", "")
    url = href if href.startswith("http") else ILIAS_BASE_URL + "/" + href.lstrip("/")

    item_type = "unknown"
    if "sendfile" in href or "ilObjFileGUI" in href:
        item_type = "file"
    elif "ilObjFolderGUI" in href:
        item_type = "folder"
    elif "target=fold" in href:
        item_type = "folder"

    # Icon-Check
    icon = el.select_one("img[alt]")
    if icon:
        alt = (icon.get("alt", "") or "").lower()
        if "datei" in alt or "file" in alt:
            item_type = "file"
        elif "ordner" in alt or "folder" in alt:
            item_type = "folder"

    # Wenn unklar: cmd=view/render = Ordner, sendfile = Datei
    if item_type == "unknown":
        if "cmd=view" in href or "cmd=render" in href:
            item_type = "folder"

    return {"name": name, "url": url, "type": item_type}


def extract_courses(soup) -> list[dict]:
    """
    Extrahiert Kurse vom HSLU ILIAS Dashboard.
    
    Struktur (aus echtem HTML):
      h4.il-item-title > a[href*="goto.php/crs/"]  → Kursname + URL
    """
    courses = []

    # HSLU Dashboard: Kurse sind in h4.il-item-title Links
    for title_el in soup.select("h4.il-item-title a"):
        href = title_el.get("href", "")
        name = title_el.get_text(strip=True)
        if name and len(name) > 2 and ("crs" in href or "ref_id" in href):
            url = href if href.startswith("http") else ILIAS_BASE_URL + "/" + href.lstrip("/")
            courses.append({"name": name, "url": url})

    # Fallback 1: ilCLI / ilObjListRow
    if not courses:
        for row in soup.select(".ilCLI, .ilObjListRow"):
            link = row.select_one("h3.il_ContainerItemTitle a, a[href*='ref_id']")
            if link and link.get("href"):
                href = link["href"]
                if "ref_id" in href:
                    url = href if href.startswith("http") else ILIAS_BASE_URL + "/" + href.lstrip("/")
                    name = link.get_text(strip=True)
                    if name and len(name) > 3:
                        courses.append({"name": name, "url": url})

    # Fallback 2: Breite Suche
    if not courses:
        for link in soup.select("a[href*='ilias.php']"):
            href = link.get("href", "")
            if "ref_id" in href and ("cmd=view" in href or "target=crs" in href):
                url = href if href.startswith("http") else ILIAS_BASE_URL + "/" + href.lstrip("/")
                name = link.get_text(strip=True)
                if name and len(name) > 3:
                    courses.append({"name": name, "url": url})

    seen = set()
    return [c for c in courses if c["url"] not in seen and not seen.add(c["url"])]


def find_course(courses: list[dict], query: str) -> dict | None:
    q = query.lower()
    for c in courses:
        if q == c["name"].lower():
            return c
    for c in courses:
        if q in c["name"].lower():
            return c
    return None


# ---------------------------------------------------------------------------
# Semesterwoche
# ---------------------------------------------------------------------------
def get_current_week_number() -> int:
    current_kw = date.today().isocalendar()[1]
    if 8 <= current_kw <= 30:
        return current_kw - 7
    elif current_kw >= 38:
        return current_kw - 37
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
async def do_scrape(course_name=None):
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    if not COOKIES_FILE.exists():
        print("❌ Keine Cookies!")
        sys.exit(1)

    cookies = json.loads(COOKIES_FILE.read_text())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        await context.add_cookies(cookies)
        page = await context.new_page()

        print("📡 Lade ILIAS Dashboard...")
        await page.goto(ILIAS_DASHBOARD_URL, timeout=PAGE_TIMEOUT)

        if "login" in page.url.lower() or "shibboleth" in page.url.lower():
            print("❌ Session abgelaufen!")
            await browser.close()
            sys.exit(1)

        # Warten bis Inhalte geladen sind (ILIAS lädt Kurse per JS nach)
        print("   ⏳ Warte auf Seiteninhalt...")
        await page.wait_for_timeout(5000)

        # Versuche auf typische ILIAS-Elemente zu warten
        try:
            await page.wait_for_selector(".ilCLI, .ilObjListRow, .il-item", timeout=10000)
        except Exception:
            print("   ⚠️  Kein typisches ILIAS-Element gefunden, versuche trotzdem...")

        html = await page.content()

        # Debug: HTML immer speichern
        Path("debug_dashboard.html").write_text(html, encoding="utf-8")
        print(f"   💾 Dashboard-HTML gespeichert ({len(html)} Zeichen)")

        soup = BeautifulSoup(html, "html.parser")
        courses = extract_courses(soup)

        print(f"📚 {len(courses)} Kurse:")
        for i, c in enumerate(courses, 1):
            print(f"  {i}. {c['name']}")

        if course_name:
            target = find_course(courses, course_name)
            if not target:
                print(f"❌ '{course_name}' nicht gefunden.")
                await browser.close()
                return

            print(f"\n🔍 Intelligentes Scraping: {target['name']}")
            result = await scrape_course_deep(page, target["url"], course_name)

            print(f"\n{'='*50}")
            print(f"📑 Ergebnis: {len(result['pdfs'])} PDFs mit Text")
            for pdf in result["pdfs"]:
                print(f"\n  📄 {pdf['name']}")
                preview = pdf["text"][:200].replace("\n", " ")
                print(f"     {preview}...")

        await browser.close()


def main():
    if len(sys.argv) < 2:
        print("  python ilias_scraper.py login")
        print("  python ilias_scraper.py scrape")
        print('  python ilias_scraper.py scrape "ANAF"')
        sys.exit(1)

    mode = sys.argv[1].lower()
    if mode == "login":
        asyncio.run(do_login())
    elif mode == "scrape":
        asyncio.run(do_scrape(sys.argv[2] if len(sys.argv) > 2 else None))
    else:
        print(f"Unbekannt: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
