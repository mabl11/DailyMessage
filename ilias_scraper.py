"""
HSLU ILIAS Scraper – Morgen-Briefing Bot
=========================================
Zwei Modi:
  1) python ilias_scraper.py login    → Öffnet Browser, du loggst dich manuell ein, Cookies werden gespeichert
  2) python ilias_scraper.py scrape   → Nutzt gespeicherte Cookies, holt Kursübersicht & Wochenmaterialien

Voraussetzungen:
  pip install playwright beautifulsoup4
  playwright install chromium
"""

import asyncio
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
COOKIES_FILE = Path("ilias_cookies.json")
ILIAS_DASHBOARD_URL = (
    "https://elearning.hslu.ch/ilias/ilias.php"
    "?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems"
)
ILIAS_BASE_URL = "https://elearning.hslu.ch"

# Timeout für Seitenladungen (in ms)
PAGE_TIMEOUT = 30_000


# ---------------------------------------------------------------------------
# Modus 1: Manueller Login – Cookies speichern
# ---------------------------------------------------------------------------
async def do_login():
    """
    Öffnet einen sichtbaren Browser. Du loggst dich manuell via SWITCHaai + 2FA ein.
    Sobald du auf der ILIAS-Startseite bist, drücke ENTER im Terminal.
    Die Session-Cookies werden dann gespeichert.
    """
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("ILIAS Login – Manueller Modus")
    print("=" * 60)
    print()
    print("Ein Browser-Fenster wird gleich geöffnet.")
    print("Bitte logge dich ganz normal via SWITCHaai + 2FA ein.")
    print("Sobald du auf der ILIAS-Startseite bist,")
    print("komm hierher zurück und drücke ENTER.")
    print()

    async with async_playwright() as p:
        # Sichtbarer Browser (headful), damit du dich einloggen kannst
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Navigiere zur ILIAS-Seite (wird auf SWITCHaai weiterleiten)
        await page.goto(ILIAS_DASHBOARD_URL, timeout=PAGE_TIMEOUT)

        # Warte auf manuellen Login
        input("\n>>> Drücke ENTER wenn du eingeloggt bist... ")

        # Cookies speichern
        cookies = await context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))
        print(f"\n✅ {len(cookies)} Cookies gespeichert in: {COOKIES_FILE}")

        # Kurzer Test: Sind wir wirklich eingeloggt?
        await page.goto(ILIAS_DASHBOARD_URL, timeout=PAGE_TIMEOUT)
        title = await page.title()
        print(f"📄 Seitentitel: {title}")

        if "ILIAS" in title or "Dashboard" in title:
            print("✅ Login erfolgreich! Cookies sind gültig.")
        else:
            print("⚠️  Konnte Login nicht verifizieren. Prüfe die Cookies.")

        await browser.close()


# ---------------------------------------------------------------------------
# Modus 2: Scrape – Kursübersicht & Wochenmaterialien holen
# ---------------------------------------------------------------------------
async def do_scrape(course_name: str | None = None):
    """
    Lädt gespeicherte Cookies, navigiert zum ILIAS Dashboard,
    extrahiert die Kursübersicht und optional die Materialien eines Kurses.
    """
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    if not COOKIES_FILE.exists():
        print("❌ Keine Cookies gefunden! Führe zuerst 'python ilias_scraper.py login' aus.")
        sys.exit(1)

    cookies = json.loads(COOKIES_FILE.read_text())
    print(f"🍪 {len(cookies)} Cookies geladen.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Cookies setzen
        await context.add_cookies(cookies)

        page = await context.new_page()

        # --- Schritt 1: Dashboard laden ---
        print(f"\n📡 Lade ILIAS Dashboard...")
        await page.goto(ILIAS_DASHBOARD_URL, timeout=PAGE_TIMEOUT)

        # Prüfe ob Session noch gültig
        current_url = page.url
        if "login" in current_url.lower() or "shibboleth" in current_url.lower():
            print("❌ Session abgelaufen! Bitte erneut einloggen:")
            print("   python ilias_scraper.py login")
            await browser.close()
            sys.exit(1)

        # --- Schritt 2: Kursübersicht extrahieren ---
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        courses = extract_courses(soup)

        if not courses:
            print("⚠️  Keine Kurse auf dem Dashboard gefunden.")
            print("    Möglicherweise hat ILIAS die HTML-Struktur geändert.")
            print("    Speichere HTML zur Analyse...")
            Path("debug_dashboard.html").write_text(html, encoding="utf-8")
            print("    → debug_dashboard.html gespeichert")
            await browser.close()
            return

        print(f"\n📚 {len(courses)} Kurse gefunden:")
        print("-" * 50)
        for i, c in enumerate(courses, 1):
            print(f"  {i}. {c['name']}")
            if c.get("url"):
                print(f"     → {c['url']}")

        # --- Schritt 3: Falls Kursname angegeben, in den Kurs navigieren ---
        if course_name:
            target = find_course(courses, course_name)
            if not target:
                print(f"\n❌ Kurs '{course_name}' nicht gefunden.")
                print("   Verfügbare Kurse:")
                for c in courses:
                    print(f"     - {c['name']}")
                await browser.close()
                return

            print(f"\n🔍 Navigiere zu: {target['name']}")
            await page.goto(target["url"], timeout=PAGE_TIMEOUT)

            # Kurze Wartezeit für dynamische Inhalte
            await page.wait_for_timeout(2000)

            course_html = await page.content()
            course_soup = BeautifulSoup(course_html, "html.parser")

            materials = extract_course_materials(course_soup)

            print(f"\n📑 Materialien in '{target['name']}':")
            print("-" * 50)
            if materials:
                for section in materials:
                    print(f"\n  📁 {section['title']}")
                    for item in section["items"]:
                        icon = get_item_icon(item.get("type", ""))
                        print(f"     {icon} {item['name']}")
                        if item.get("description"):
                            print(f"        {item['description'][:80]}...")
            else:
                print("  Keine strukturierten Materialien gefunden.")
                print("  Speichere HTML zur Analyse...")
                Path("debug_course.html").write_text(course_html, encoding="utf-8")
                print("  → debug_course.html gespeichert")

            # Ergebnis als JSON speichern
            result = {
                "course": target["name"],
                "scraped_at": datetime.now().isoformat(),
                "materials": materials,
            }
            out_file = Path(f"course_materials_{slugify(target['name'])}.json")
            out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"\n💾 Ergebnis gespeichert: {out_file}")

        await browser.close()


# ---------------------------------------------------------------------------
# HTML-Parsing Helpers
# ---------------------------------------------------------------------------
def extract_courses(soup: "BeautifulSoup") -> list[dict]:
    """
    Extrahiert Kurse vom ILIAS Dashboard.
    ILIAS nutzt verschiedene HTML-Strukturen je nach Version –
    wir versuchen mehrere Selektoren.
    """
    courses = []

    # Strategie 1: Kurs-Container mit "il-item" Klasse (neueres ILIAS)
    for item in soup.select(".il-item"):
        link = item.select_one("a")
        if link and link.get("href"):
            url = link["href"]
            if not url.startswith("http"):
                url = ILIAS_BASE_URL + "/" + url.lstrip("/")
            courses.append({
                "name": link.get_text(strip=True),
                "url": url,
            })

    # Strategie 2: Kurs-Links in der "Meine Kurse" Sektion
    if not courses:
        for link in soup.select("a[href*='ilias.php']"):
            href = link.get("href", "")
            # Kurse haben typisch "ref_id" und "target=crs" in der URL
            if "ref_id" in href and ("cmd=view" in href or "target=crs" in href):
                url = href if href.startswith("http") else ILIAS_BASE_URL + "/" + href.lstrip("/")
                name = link.get_text(strip=True)
                if name and len(name) > 3:  # Filtere leere Links
                    courses.append({"name": name, "url": url})

    # Strategie 3: Breitere Suche – alle Links mit "Kurs" oder "crs" Referenz
    if not courses:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "crs" in href or "Kurs" in link.get_text():
                url = href if href.startswith("http") else ILIAS_BASE_URL + "/" + href.lstrip("/")
                name = link.get_text(strip=True)
                if name and len(name) > 3:
                    courses.append({"name": name, "url": url})

    # Duplikate entfernen (nach URL)
    seen = set()
    unique = []
    for c in courses:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)

    return unique


def extract_course_materials(soup: "BeautifulSoup") -> list[dict]:
    """
    Extrahiert Materialien/Sektionen aus einer Kursseite.
    ILIAS strukturiert Kurse typisch in Ordner, Lernmodule, Dateien etc.
    """
    sections = []

    # Suche nach Content-Containern (Ordner / Sektionen)
    # ILIAS groupiert Inhalte oft in "ilContainerBlock" oder "il-item-group"
    containers = soup.select(".ilContainerBlock, .il-item-group, .ilCLI")

    if containers:
        for container in containers:
            # Sektions-Titel
            title_el = container.select_one(
                ".ilContainerBlockHeader, .il-item-group-title, h3, h4"
            )
            title = title_el.get_text(strip=True) if title_el else "Ohne Titel"

            items = []
            for item_el in container.select(".il-item, .ilCLI, .ilObjListRow"):
                item = parse_item(item_el)
                if item:
                    items.append(item)

            if items:
                sections.append({"title": title, "items": items})

    # Fallback: Alle Items direkt sammeln
    if not sections:
        items = []
        for item_el in soup.select(".il-item, .ilObjListRow"):
            item = parse_item(item_el)
            if item:
                items.append(item)
        if items:
            sections.append({"title": "Alle Materialien", "items": items})

    return sections


def parse_item(el) -> dict | None:
    """Parst ein einzelnes ILIAS-Item (Datei, Ordner, Lernmodul etc.)."""
    link = el.select_one("a")
    if not link:
        return None

    name = link.get_text(strip=True)
    if not name or len(name) < 2:
        return None

    href = link.get("href", "")
    url = href if href.startswith("http") else ILIAS_BASE_URL + "/" + href.lstrip("/")

    # Typ erkennen
    item_type = "unknown"
    classes = " ".join(el.get("class", []))
    href_lower = href.lower()

    if "file" in href_lower or "file" in classes:
        item_type = "file"
    elif "fold" in href_lower or "folder" in classes:
        item_type = "folder"
    elif "lm" in href_lower or "htlm" in href_lower:
        item_type = "learning_module"
    elif "exc" in href_lower:
        item_type = "exercise"
    elif "tst" in href_lower:
        item_type = "test"
    elif "frm" in href_lower:
        item_type = "forum"

    # Beschreibung
    desc_el = el.select_one(".il-item-description, .ilListItemDescription, .il_Description")
    description = desc_el.get_text(strip=True) if desc_el else None

    return {
        "name": name,
        "url": url,
        "type": item_type,
        "description": description,
    }


def find_course(courses: list[dict], query: str) -> dict | None:
    """Findet einen Kurs per (Teil-)Name, case-insensitive."""
    query_lower = query.lower()
    # Exakter Match zuerst
    for c in courses:
        if query_lower == c["name"].lower():
            return c
    # Teilstring-Match
    for c in courses:
        if query_lower in c["name"].lower():
            return c
    return None


def get_item_icon(item_type: str) -> str:
    """Emoji-Icon für ILIAS-Itemtypen."""
    icons = {
        "file": "📄",
        "folder": "📁",
        "learning_module": "📖",
        "exercise": "✏️",
        "test": "📝",
        "forum": "💬",
    }
    return icons.get(item_type, "📎")


def slugify(text: str) -> str:
    """Einfacher Slugify für Dateinamen."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "_", text)
    return text[:50]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Verwendung:")
        print("  python ilias_scraper.py login              → Manueller Login, Cookies speichern")
        print("  python ilias_scraper.py scrape              → Kursübersicht holen")
        print('  python ilias_scraper.py scrape "Kursname"   → Materialien eines Kurses holen')
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "login":
        asyncio.run(do_login())
    elif mode == "scrape":
        course = sys.argv[2] if len(sys.argv) > 2 else None
        asyncio.run(do_scrape(course))
    else:
        print(f"Unbekannter Modus: {mode}")
        print("Verwende 'login' oder 'scrape'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
